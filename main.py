# main.py

import io
import os
import shutil
import tempfile
import pandas as pd

from contextlib import asynccontextmanager
from fastapi import FastAPI, Header, HTTPException, Depends, UploadFile, File, Form
from fastapi.responses import StreamingResponse, HTMLResponse
from pydantic import BaseModel

from config import config, pool
from db.ccs import init_db
from content.own import init_db_own, import_from_excel
from content.viral import init_db_viral
from tools.check_originality import _check_similarity, auto_revise

import agent

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时：打开连接池
    await pool.open()
    print("数据库连接池已打开")
    await init_db()
    await init_db_own()
    await init_db_viral()
    print("三张表已就绪")
    yield
    # 关闭时：关闭连接池
    await pool.close()
    print("数据库连接池已关闭")


app = FastAPI(lifespan=lifespan)

class ChatRequest(BaseModel):
    user_id: str
    user_input: str


_HTML_PATH = os.path.join(os.path.dirname(__file__), "index.html")
_HTML_CACHE = None


async def verify_key(x_auth_key: str = Header(...)):
    if not config.AUTH_KEY:
        raise HTTPException(status_code=503, detail="服务未开放")
    if x_auth_key != config.AUTH_KEY:
        raise HTTPException(status_code=401, detail="Invalid Auth Key")


@app.get("/", response_class=HTMLResponse)
async def index():
    global _HTML_CACHE
    if _HTML_CACHE is None:
        with open(_HTML_PATH, "r", encoding="utf-8") as f:
            _HTML_CACHE = f.read()
    return HTMLResponse(_HTML_CACHE.replace("__AUTH_KEY__", config.AUTH_KEY))


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/chat_stream")
async def chat_stream(
    request: ChatRequest,
    _: str = Depends(verify_key),
):
    if len(request.user_input) > config.MAX_INPUT_LENGTH:
        raise HTTPException(
            status_code=413,
            detail=f"输入过长，最多 {config.MAX_INPUT_LENGTH} 字"
        )
    return StreamingResponse(
        agent.chat_stream(request.user_id, request.user_input),
        media_type="text/plain"
    )





@app.get("/export_own_articles")
async def export_own_articles(_: str = Depends(verify_key)):
    from config import pool
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                SELECT id, title, content, platform, publish_date,
                       views, likes, collects, comments, shares, followers_gained
                FROM own_articles
                ORDER BY id DESC
            """)
            rows = await cur.fetchall()
            cols = [d.name for d in cur.description]

    df = pd.DataFrame(rows, columns=cols)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="own_articles")
    output.seek(0)

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=own_articles_export.xlsx"}
    )


@app.get("/export_viral_articles")
async def export_viral_articles(_: str = Depends(verify_key)):
    from config import pool
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                SELECT id, title, content, author, author_followers,platform, 
                       note_url, likes, collects, comments, publish_date, collected_date
                FROM viral_articles
                ORDER BY id DESC
            """)
            rows = await cur.fetchall()
            cols = [d.name for d in cur.description]

    df = pd.DataFrame(rows, columns=cols)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="viral_articles")
    output.seek(0)

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=viral_articles_export.xlsx"}
    )

@app.post("/import_own_articles")
async def import_own_articles(
    file: UploadFile = File(...),
    _: str = Depends(verify_key),
):
    tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
    tmp_path = tmp.name
    try:
        shutil.copyfileobj(file.file, tmp)
        tmp.close()
        await import_from_excel(tmp_path)
        return {"msg": "Excel 导入成功"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导入失败：{str(e)}")
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

@app.post("/import_viral_articles")
async def import_viral_articles_api(
    file: UploadFile = File(...),
    _: str = Depends(verify_key),
):
    from content.viral import import_from_excel_viral
    tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
    tmp_path = tmp.name
    try:
        shutil.copyfileobj(file.file, tmp)
        tmp.close()
        result = await import_from_excel_viral(tmp_path)
        return {
            "msg": f"导入成功：{result['success']}/{result['total']} 条（跳过 {result['skipped']} 条）"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导入失败：{str(e)}")
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


@app.post("/check_originality")
async def check_originality_api(
    text: str = Form(...),
    _: str = Depends(verify_key),
):
    r = await _check_similarity(text)
    if r.get("error"):
        return {"result": f"⚠️ {r['error']}", "similarity": 0.0, "ok": True}
    return {
        "result": f"相似度 {r['similarity']:.2%}",
        "similarity": r["similarity"],
        "ok": r["ok"],
    }


@app.post("/auto_revise")
async def auto_revise_api(
    text: str = Form(...),
    _: str = Depends(verify_key),
):
    result = await auto_revise(text)
    return {"result": result}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)