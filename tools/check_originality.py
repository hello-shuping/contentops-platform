# tools/check_originality.py
# 原创度检测 + 自动改写

import json
import httpx
from openai import AsyncOpenAI
from config import config, pool


_llm = AsyncOpenAI(api_key=config.API_KEY, base_url=config.BASE_URL)


# ---------- 内部：结构化检测 ----------

async def _check_similarity(text: str) -> dict:
    """返回 {'ok': bool, 'similarity': float, 'matched': str, 'error': str}"""
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT title || ' ' || COALESCE(content, '') FROM viral_articles LIMIT 100"
            )
            rows = await cur.fetchall()

    candidates = [r[0] for r in rows]

    if not candidates:
        return {"ok": True, "similarity": 0.0, "matched": "", "error": "爆文库为空，先爬一批"}

    candidates = [c[:1500] for c in candidates]

    payload = {
        "appKey": config.SHOWAPI_APPKEY,
        "t1": text[:1500],
        "t2": json.dumps(candidates, ensure_ascii=False),
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post("https://route.showapi.com/294-2", data=payload)
            result = resp.json()
    except Exception as e:
        return {"ok": True, "similarity": 0.0, "matched": "", "error": str(e)}

    body = result.get("showapi_res_body", {})
    if body.get("ret_code") != 0:
        return {"ok": True, "similarity": 0.0, "matched": "", "error": body.get("remark", "接口错误")}

    idx = body.get("mostLike")
    val = body.get("likeValue")
    if idx is None or val is None:
        return {"ok": True, "similarity": 0.0, "matched": ""}

    val = float(val)
    matched = candidates[idx] if 0 <= idx < len(candidates) else ""
    return {"ok": val < 0.65, "similarity": val, "matched": matched}


# ---------- 对外：自动改写到达标 ----------

async def auto_revise(text: str, max_rounds: int = 1, threshold: float = 0.65) -> str:
    history = []

    for i in range(max_rounds):
        r = await _check_similarity(text)
        if r.get("error"):
            return f"❌ 检测出错：{r['error']}"
        history.append(r["similarity"])

        if r["ok"]:
            sims = " → ".join(f"{s:.2%}" for s in history)
            return (
                f"✅ 已达标（改写 {i} 轮）\n"
                f"相似度变化：{sims}\n\n"
                f"【最终文章】\n{text}"
            )

        matched = r["matched"][:800]
        prompt = f"""请改写下面这篇文章，保持原意和风格不变，但换一种表达方式，避免与已有内容雷同。

参考：以下是库中与原文最相似的片段，请避开这些表达和结构：
{matched}

原文：
{text}

只输出改写后的文章，不要任何说明。"""

        resp = await _llm.chat.completions.create(
            model=config.MODEL,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.choices[0].message.content.strip()

    sims = " → ".join(f"{s:.2%}" for s in history)
    return (
        f"⚠️ 已改写 {max_rounds} 轮仍未达标\n"
        f"相似度变化：{sims}\n\n"
        f"【当前版本】\n{text}"
    )