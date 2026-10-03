# db/ccs.py

from datetime import datetime
from config import pool


async def init_db():
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id SERIAL PRIMARY KEY,
                    user_id TEXT,
                    user_input TEXT,
                    ai_reply TEXT,
                    created_at TIMESTAMP
                )
            """)


async def save_to_db(user_id, user_input, ai_reply):
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO conversations (user_id, user_input, ai_reply, created_at) VALUES (%s, %s, %s, %s)",
                (user_id, user_input, ai_reply, datetime.now())
            )


async def load_history(user_id: str, limit: int = 5, system_prompt: str = ""):
    """
    加载用户最近 limit 条历史记录
    """
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT user_input, ai_reply FROM conversations WHERE user_id = %s ORDER BY created_at DESC LIMIT %s",
                (user_id, limit)
            )
            rows = await cur.fetchall()

    rows.reverse()

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    for user_msg, ai_msg in rows:
        messages.append({"role": "user", "content": user_msg})
        messages.append({"role": "assistant", "content": ai_msg})
    return messages


async def clear_history(user_id):
    """删除某个用户的所有对话记录"""
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("DELETE FROM conversations WHERE user_id = %s", (user_id,))