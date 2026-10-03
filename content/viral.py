# content/viral.py

import asyncio
from openai import OpenAI
from config import config, pool
from content.redfox import search_xhs_notes


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


# ========== 4. 单条写入 ==========
async def save_viral_note(note: dict):
    """把一条红狐笔记存入 viral_articles"""
    title = note.get("workTitle", "")
    content = note.get("workDesc", "")

    embedding = get_embedding(f"{title}\n{content}")

    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                INSERT INTO viral_articles
                (work_id, title, content, author, author_followers, platform,
                 note_url, likes, collects, comments, embedding)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (work_id) DO NOTHING
            """, (
                note.get("workId"),
                title,
                content,
                note.get("accountNickname"),
                0,
                "小红书",
                note.get("workUrl"),
                note.get("workLikedCount"),
                note.get("workCollectedCount"),
                note.get("workCommentsCount"),
                embedding,
            ))


# ========== 5. 批量抓取 ==========
async def fetch_and_save(keyword: str, limit: int = 20):
    """搜一批红狐笔记，存进数据库"""
    # 红狐 SDK 是同步的，扔到别的线程去跑，别阻塞事件循环
    notes = await asyncio.to_thread(search_xhs_notes, keyword, "4", limit)

    inserted = 0
    skipped = 0

    for note in notes:
        work_id = note.get("workId")
        try:
            async with pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "SELECT 1 FROM viral_articles WHERE work_id = %s",
                        (work_id,)
                    )
                    exists = await cur.fetchone() is not None

            if exists:
                skipped += 1
                continue

            await save_viral_note(note)
            inserted += 1
            print(f"✅ {note.get('workTitle')}")
        except Exception as e:
            print(f"❌ 失败: {e}")

    print(f"新增 {inserted} 条，跳过重复 {skipped} 条")
    return {"total": len(notes), "success": inserted, "skipped": skipped}


# ========== 6. 检索 ==========
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