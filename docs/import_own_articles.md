# 功能文档 · 导入自己的文章

> 状态：v1，代码地图和数据结构完整，失败场景待补
> 最后更新：2026-10-01
> 对应代码版本：contentops-platform 多平台重构前

---

## 目录

- [一、代码地图](#一代码地图)
- [二、接口卡片](#二接口卡片)
- [三、数据结构与格式转换](#三数据结构与格式转换)
- [四、触发条件](#四触发条件)
- [五、成功路径](#五成功路径)
- [六、失败场景与处理](#六失败场景与处理)
- [七、边界情况](#七边界情况)
- [八、测试用例](#八测试用例)
- [九、已知问题与坑](#九已知问题与坑)
- [十、变更历史](#十变更历史)

---

# 第一节 · 代码地图

## 调用链路

```
【前端 · index.html】
  │
  ├─ 按钮
  │    onclick="document.getElementById('excelInput').click()"
  │
  ├─ 隐藏输入框
  │    <input type="file" id="excelInput" onchange="uploadExcel()">
  │
  └─ 上传函数 uploadExcel()
       │
       │  fetch("/import_own_articles", {
       │      method: "POST",
       │      headers: {"X-Auth-Key": AUTH_KEY},
       │      body: formData
       │  })
       ▼
【路由层 · main.py】
  │
  └─ @app.post("/import_own_articles")
     async def import_own_articles(
         file: UploadFile = File(...),
         _: str = Depends(verify_key),
     ):
       │
       ├─ 1. verify_key                          鉴权
       ├─ 2. tempfile.NamedTemporaryFile         建临时文件
       ├─ 3. shutil.copyfileobj                  上传内容复制进临时文件
       ├─ 4. await import_from_excel(tmp_path)   直接 await
       └─ 5. finally: os.unlink(tmp_path)        删临时文件
            ▼
【数据层 · content/own.py】
  │
  └─ async def import_from_excel(path):
       │
       ├─ 1. DELETE FROM own_articles            清空旧数据
       ├─ 2. pd.read_excel(path)                 读 Excel
       └─ 3. for row in df:
            │
            └─ save_article(...)
                 ├─ get_embedding(...)           调千问转向量（同步）
                 └─ INSERT INTO own_articles
```

## 涉及的函数与文件

| 位置 | 函数 | 说明 |
|---|---|---|
| index.html | `uploadExcel()` | 打包文件、发请求 |
| main.py | `import_own_articles` | 接口函数 |
| main.py | `verify_key` | 鉴权（被 Depends 调） |
| content/own.py | `import_from_excel` | 业务函数，async |
| content/own.py | `save_article` | 逐条入库 |
| content/own.py | `get_embedding` | 调千问 embedding，同步 |
| 外部 | 千问 embedding API | 文本转向量 |

## 一个隐藏的阻塞点

`get_embedding` 是同步函数：

```python
def get_embedding(text):                                 # 没有 async
    response = embedding_client.embeddings.create(...)   # 同步调用
```

**后果**：导入过程中每条文章的向量化会阻塞事件循环几百毫秒。

**规模**：100 条文章 ≈ 阻塞几十秒。

**定性**：量小、非高频操作，暂不处理。等真卡了再改。

# 第二节 · 接口卡片

## 基本信息

| 项 | 内容 |
|---|---|
| 路径 | `/import_own_articles` |
| 方法 | POST |
| 鉴权 | 需要 `X-Auth-Key` header |
| 触发方式 | 前端「导入」按钮 |
| 功能 | 上传 Excel，全量覆盖 `own_articles` 表 |

## 请求

### 请求头

| 字段 | 值 | 必须 |
|---|---|---|
| X-Auth-Key | 与 `.env` 中 AUTH_KEY 一致 | 是 |
| Content-Type | multipart/form-data | 是（浏览器自动带） |

### 请求体（multipart/form-data）

| 字段 | 类型 | 说明 |
|---|---|---|
| file | 文件 | .xlsx 格式，表头需符合约定 |

## 响应

| 状态码 | 场景 | 返回体 |
|---|---|---|
| 200 | 导入成功 | `{"msg": "Excel 导入成功"}` |
| 401 | AUTH_KEY 不匹配 | `{"detail": "Invalid Auth Key"}` |
| 422 | 缺少 X-Auth-Key header 或 file 字段 | FastAPI 自动生成的校验错误 |
| 500 | 导入过程出错 | `{"detail": "导入失败：{具体错误}"}` |
| 503 | 服务端 AUTH_KEY 未配置 | `{"detail": "服务未开放"}` |

**关于 422**：不是代码里写的，是 FastAPI 框架自动产生的。
当请求缺少必需的 header 或字段时，路由函数还没执行就被拦截，返回 422 和一份校验错误详情。

## 后端流程

```
① verify_key 鉴权
② 上传内容写入 /tmp/tmpXXXX.xlsx
③ await import_from_excel(tmp_path)
④ finally 删除临时文件
```

## 数据库影响

| 表 | 操作 |
|---|---|
| own_articles | 先 DELETE 全部，再逐行 INSERT |

每行含 1024 维 embedding 字段（来自千问 embedding API）。

## 性能

| 规模 | 预估耗时 |
|---|---|
| 20 条 | ≈ 10 秒 |
| 100 条 | ≈ 50 秒 |
| 500 条 | ≈ 4-5 分钟 |

主要耗时在每条文章调一次 embedding API。代码里有 `time.sleep(0.5)` 防限流。

## 修改路径时需同步改

| 文件 | 位置 |
|---|---|
| index.html | `fetch("/import_own_articles", ...)` |
| main.py | `@app.post("/import_own_articles")` |


