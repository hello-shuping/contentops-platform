# content/own.py

import asyncio
import pandas as pd
from openai import OpenAI
from config import config, pool


# ========== 1. 建表 ==========
async def init_db_own():
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS own_articles (
                    id SERIAL PRIMARY KEY,
                    title TEXT,
                    content TEXT,
                    platform TEXT,
                    publish_date DATE,
                    views INTEGER,
                    likes INTEGER,
                    collects INTEGER,
                    comments INTEGER,
                    shares INTEGER,
                    followers_gained INTEGER,
                    embedding vector(1024),
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
    response = embedding_client.embeddings.create(
        model=config.EMBEDDING_MODEL,
        input=text,
    )
    return response.data[0].embedding


# ========== 4. 单条写入 ==========
async def save_article(title, content, platform, publish_date,
                       views, likes, collects, comments, shares, followers_gained):
    embedding = get_embedding(f"{title}\n{content}")

    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                INSERT INTO own_articles
                (title, content, platform, publish_date, views, likes,
                 collects, comments, shares, followers_gained, embedding)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (title, content, platform, publish_date,
                  views, likes, collects, comments, shares, followers_gained, embedding))


# ========== 5. 批量导入 ==========
async def import_from_excel(path):
    # 清空表
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("DELETE FROM own_articles")

    df = pd.read_excel(path)
    print(f"共 {len(df)} 行")

    success = 0
    for i, row in df.iterrows():
        try:
            await save_article(
                title=str(row["title"]).strip(),
                content=str(row["content"]).replace("|||", "\n\n"),
                platform=str(row.get("platform", "小红书")),
                publish_date=row.get("publish_date"),
                views=int(row.get("views", 0) or 0),
                likes=int(row.get("likes", 0) or 0),
                collects=int(row.get("collects", 0) or 0),
                comments=int(row.get("comments", 0) or 0),
                shares=int(row.get("shares", 0) or 0),
                followers_gained=int(row.get("followers_gained", 0) or 0),
            )
            success += 1
            print(f"✅ {i+1}/{len(df)}：{row['title']}")
            await asyncio.sleep(0.5)
        except Exception as e:
            print(f"❌ 第 {i+2} 行失败：{e}")

    print(f"\n导入完成：成功 {success}/{len(df)}")
    return {"total": len(df), "success": success}


# ========== 6. 检索 ==========
async def search_own_articles(query, limit=5):
    query_embedding = get_embedding(query)

    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                SELECT title, content FROM own_articles
                ORDER BY embedding <=> %s::vector
                LIMIT %s
            """, (query_embedding, limit))
            rows = await cur.fetchall()

    return [{"title": r[0], "content": r[1]} for r in rows]


# ========== 7. 统计 ==========
async def get_stats_summary(platform=None):
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            sql = """
                SELECT
                    title, platform, views, likes, collects, comments,
                    ROUND((likes + collects + comments)::numeric / NULLIF(views, 0) * 100, 2) AS 互动率,
                    ROUND(collects::numeric / NULLIF(views, 0) * 100, 2) AS 收藏率
                FROM own_articles
            """
            if platform:
                sql += " WHERE platform = %s ORDER BY 互动率 DESC"
                await cur.execute(sql, (platform,))
            else:
                sql += " ORDER BY 互动率 DESC"
                await cur.execute(sql)

            rows = await cur.fetchall()

    result = []
    for r in rows:
        result.append({
            "title": r[0],
            "platform": r[1],
            "views": r[2],
            "likes": r[3],
            "collects": r[4],
            "comments": r[5],
            "互动率": float(r[6]) if r[6] else 0,
            "收藏率": float(r[7]) if r[7] else 0,
        })
    return result