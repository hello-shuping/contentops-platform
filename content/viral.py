# content/viral.py

from openai import OpenAI
from config import config, pool


# ========== 1. 建表 ==========
async def init_db_viral():
    """建爆文表"""
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS viral_articles (
                    id SERIAL PRIMARY KEY,
                    work_id TEXT UNIQUE,
                    title TEXT,
                    content TEXT,
                    author TEXT,
                    author_followers INTEGER,
                    platform TEXT DEFAULT '小红书',
                    note_url TEXT,
                    likes INTEGER,
                    collects INTEGER,
                    comments INTEGER,
                    embedding vector(1024),
                    publish_date DATE,
                    collected_date DATE DEFAULT CURRENT_DATE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)


# ========== 2. 全局客户端 ==========
embedding_client = OpenAI(
    api_key=config.EMBEDDING_API_KEY,
    base_url=config.EMBEDDING_BASE_URL,
)


# ========== 3. 文本 → 向量 ==========
def get_embedding(text):
    """把文字转成向量"""
    response = embedding_client.embeddings.create(
        model=config.EMBEDDING_MODEL,
        input=text,
    )
    return response.data[0].embedding


# ========== 4. 手动采集爆文导入 ==========
async def import_from_excel_viral(path):
    """
    从 Excel 导入手动采集的爆文。
    表头：title, content, publish_time, likes, collects, comments, followers
    """
    import pandas as pd
    from datetime import date, timedelta
    import hashlib
    import asyncio

    def parse_publish_time(tag):
        tag = str(tag).strip().lower()
        today = date.today()
        try:
            if tag.endswith("d"):
                return today - timedelta(days=int(tag[:-1]))
            elif tag.endswith("w"):
                return today - timedelta(weeks=int(tag[:-1]))
            elif tag.endswith("m"):
                return today - timedelta(days=int(tag[:-1]) * 30)
        except (ValueError, IndexError):
            pass
        return None

    def safe_int(val, default=0):
        if pd.isna(val):
            return default
        try:
            return int(float(val))
        except (ValueError, TypeError):
            return default

    def make_work_id(title):
        return "manual_" + hashlib.md5(title.encode("utf-8")).hexdigest()[:16]

    df = pd.read_excel(path)

    success = 0
    skipped = 0

    for i, row in df.iterrows():
        title = str(row.get("title", "")).strip()
        if not title or title == "nan":
            skipped += 1
            continue

        content = str(row.get("content", "")).strip()
        if content == "nan":
            content = ""

        publish_date = parse_publish_time(row.get("publish_time", ""))
        likes = safe_int(row.get("likes"))
        collects = safe_int(row.get("collects"))
        comments = safe_int(row.get("comments"))
        followers = safe_int(row.get("followers"))

        work_id = make_work_id(title)
        embedding = get_embedding(f"{title}\n{content}")

        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    INSERT INTO viral_articles
                    (work_id, title, content, author_followers, platform,
                     likes, collects, comments, embedding, publish_date)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (work_id) DO NOTHING
                """, (
                    work_id, title, content, followers, "小红书",
                    likes, collects, comments, embedding, publish_date
                ))
                # 用 rowcount 判断是否真的插入了
                if cur.rowcount > 0:
                    success += 1
                else:
                    skipped += 1

        await asyncio.sleep(0.5)

    return {"total": len(df), "success": success, "skipped": skipped}


# ========== 5. 检索 ==========
async def search_viral_articles(query: str, limit: int = 5):
    """先按向量粗筛，再按点赞排序取前 N 条"""
    query_embedding = get_embedding(query)

    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                SELECT title, content, author, likes
                FROM viral_articles
                ORDER BY embedding <=> %s::vector
                LIMIT %s
            """, (query_embedding, max(20, limit)))
            rows = await cur.fetchall()

    results = [
        {"title": r[0], "content": r[1], "author": r[2], "likes": r[3]}
        for r in rows
    ]
    results.sort(key=lambda x: x["likes"] or 0, reverse=True)
    return results[:limit]