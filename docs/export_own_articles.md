# 功能文档 · 导出自己的文章

> 状态：v1
> 最后更新：2026-10-01

---

## 第一节 · 代码地图

### 调用链路

```
【前端 · index.html】
  │
  ├─ 按钮
  │    <button onclick="downloadExcel()">导出</button>
  │
  └─ 下载函数 downloadExcel()
       │
       │  fetch("/export_own_articles", {
       │      method: "GET",
       │      headers: {"X-Auth-Key": AUTH_KEY}
       │  })
       ▼
【路由层 · main.py】
  │
  └─ @app.get("/export_own_articles")
     async def export_own_articles(_: str = Depends(verify_key)):
       │
       ├─ 1. verify_key                    鉴权
       ├─ 2. 从连接池取连接
       ├─ 3. SELECT 查询 own_articles
       ├─ 4. 取出行数据 + 列名
       ├─ 5. 构造 DataFrame
       ├─ 6. 写入 io.BytesIO（内存中的虚拟文件）
       └─ 7. StreamingResponse 返回二进制流
            ▼
【前端 · downloadExcel()】
  │
  ├─ 收到 blob（二进制）
  ├─ 创建临时 <a> 标签
  ├─ 触发下载
  └─ 保存成 own_articles_export.xlsx
```

### 涉及的函数与文件

| 位置 | 函数 | 说明 |
|---|---|---|
| index.html | `downloadExcel()` | 发请求、接收 blob、触发下载 |
| main.py | `export_own_articles` | 接口函数 |
| main.py | `verify_key` | 鉴权（被 Depends 调） |
| config.py | `pool` | 数据库连接池 |
| 外部 | 无 | 不调任何外部 API |

### 关键特征

**和导入的最大区别**：导出**不调外部 API**。

- 导入：每条文章调一次千问 embedding 转向量
- 导出：只查库 + 生成 Excel + 返回

**所以导出快**。1000 条数据也就 1-2 秒。没有限流问题、没有花钱问题。

### 架构上的一个瑕疵

**导出的 SQL 内联在 `main.py` 里，没走 `content/` 层。**

对比一下：

```
导入：main.py 路由 → content/own.py 的 import_from_excel
导出：main.py 路由 → 直接 pd.read_sql（没有中间层）
```

为什么导出这样写？因为导出的逻辑很简单——查库 + 转 Excel，没有业务加工。放 `content/` 里只会多一层调用，没有实质好处。

但如果你想统一风格，可以挪。**现在不用动。**

---

## 第二节 · 接口卡片

### 基本信息

| 项 | 内容 |
|---|---|
| 路径 | `/export_own_articles` |
| 方法 | GET |
| 鉴权 | 需要 `X-Auth-Key` header |
| 触发方式 | 前端「导出」按钮 |
| 功能 | 从 `own_articles` 表导出全部数据为 xlsx |

### 请求

**请求头**

| 字段 | 值 | 必须 |
|---|---|---|
| X-Auth-Key | 与 `.env` 中 AUTH_KEY 一致 | 是 |

**请求体**：无（GET 请求）

**请求参数**：无

### 响应

| 状态码 | 场景 | 返回体 |
|---|---|---|
| 200 | 导出成功 | xlsx 二进制流 |
| 401 | AUTH_KEY 不匹配 | `{"detail": "Invalid Auth Key"}` |
| 422 | 缺少 X-Auth-Key header | FastAPI 自动生成的校验错误 |
| 503 | 服务端 AUTH_KEY 未配置 | `{"detail": "服务未开放"}` |
| 500 | 数据库查询失败 | FastAPI 默认错误响应 |

**200 响应的头部：**

```
Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet
Content-Disposition: attachment; filename=own_articles_export.xlsx
```

浏览器看到 `Content-Disposition: attachment`，会自动触发下载。文件名由 `filename=` 指定。

### 后端流程

```
① verify_key 鉴权
② 从连接池取连接
③ 执行 SELECT 查询
④ 取出 rows + cols
⑤ pd.DataFrame(rows, columns=cols)
⑥ pd.ExcelWriter 写入 io.BytesIO
⑦ output.seek(0) 把读写指针移回开头
⑧ return StreamingResponse(output, ...)
```

### 数据库影响

| 表 | 操作 |
|---|---|
| own_articles | 只读（SELECT） |

**导出不影响数据。** 表里的内容不会变。

### 导出字段

```
id, title, content, platform, publish_date,
views, likes, collects, comments, shares, followers_gained
```

**共 11 列。** `embedding` 字段**不导出**（1024 维向量，无意义且巨大）。

### 性能

| 规模 | 预估耗时 |
|---|---|
| 100 条 | < 1 秒 |
| 1000 条 | 1-2 秒 |
| 10000 条 | 3-5 秒 |

主要耗时在数据库查询和 Excel 生成。**不涉及任何外部 API 调用**，所以没有限流问题。

### 修改路径时需同步改

| 文件 | 位置 |
|---|---|
| index.html | `fetch("/export_own_articles", ...)` |
| main.py | `@app.get("/export_own_articles")` |

---

## 第三节 · 数据结构与格式转换

### 流转总览

```
① 数据库行（PostgreSQL 查询结果）
      ↓ cursor.fetchall()
② Python 元组列表
      ↓ cursor.description 取列名
③ 列名列表
      ↓ pd.DataFrame(rows, columns=cols)
④ pandas DataFrame
      ↓ df.to_excel(writer, ...)
⑤ Excel 二进制字节
      ↓ io.BytesIO
⑥ 内存中的虚拟文件
      ↓ output.seek(0)
⑦ StreamingResponse
      ↓ HTTP
⑧ 前端 blob
      ↓ createObjectURL + a.click()
⑨ 用户磁盘上的 .xlsx 文件
```

**和导入对比：8 站 vs 9 站。** 但导出的转换比导入简单得多——没有文件上传、没有临时文件、没有向量化。

---

### ① → ②：数据库行 → Python 元组列表

**代码**：

```python
await cur.execute("""
    SELECT id, title, content, platform, publish_date,
           views, likes, collects, comments, shares, followers_gained
    FROM own_articles
    ORDER BY id DESC
""")
rows = await cur.fetchall()
```

**数据形态**：

```python
[
    (1, "考研英语怎么学", "正文...", "小红书", date(2025,1,15), 1200, 85, 42, 10, 5, 3),
    (2, "政治选择题技巧", "正文...", "小红书", date(2025,1,14), 800, 42, 20, 8, 2, 1),
    ...
]
```

**关键点**：

- `fetchall()` 返回**元组列表**，不是字典列表
- 每行是一个元组，字段顺序和 SELECT 的列顺序一致
- 时间字段返回的是 `datetime.date` 对象
- 数值字段返回的是 Python `int`

**和导入的区别**：导入时数据从 Excel 来（字符串为主），导出时数据从数据库来（类型已经正确）。

---

### ② → ③：取列名

**代码**：

```python
cols = [d.name for d in cur.description]
```

**数据形态**：

```python
['id', 'title', 'content', 'platform', 'publish_date',
 'views', 'likes', 'collects', 'comments', 'shares', 'followers_gained']
```

**关键点**：

- `cur.description` 是 psycopg 返回的"列元数据"
- 每个元素有 `.name` 属性，就是列名
- 这一步**必须有**——因为 `fetchall()` 只给数据，不给列名。没有列名，DataFrame 就不知道每列叫什么

**和导入的区别**：导入时列名来自 Excel 表头，导出时列名来自 SQL 的列（自动取）。

---

### ③ + ④ → ⑤：DataFrame → Excel 字节

**代码**：

```python
df = pd.DataFrame(rows, columns=cols)

output = io.BytesIO()
with pd.ExcelWriter(output, engine="openpyxl") as writer:
    df.to_excel(writer, index=False, sheet_name="own_articles")
output.seek(0)
```

**数据形态**：

```
DataFrame
┌────┬──────────────────┬─────────────┬──────────┬────────┬───────┐
│ id │ title            │ content     │ platform │ views  │ likes │
├────┼──────────────────┼─────────────┼──────────┼────────┼───────┤
│ 1  │ 考研英语怎么学    │ 正文...     │ 小红书   │ 1200   │ 85    │
│ 2  │ 政治选择题技巧    │ 正文...     │ 小红书   │ 800    │ 42    │
└────┴──────────────────┴─────────────┴──────────┴────────┴───────┘
```

**`io.BytesIO()` 是什么**：

- 一个"内存中的虚拟文件"
- 不需要落盘，直接生成字节流
- 对导出很合适——数据量小，不需要磁盘 IO

**`pd.ExcelWriter` 是什么**：

- pandas 提供的 Excel 写入器
- 告诉 pandas "把数据写到哪、用什么引擎"
- `engine="openpyxl"` 是 Excel 的写入引擎

**`index=False` 是什么**：

- pandas 默认会给 DataFrame 加一列"行号"（0, 1, 2...）
- `index=False` 告诉它"不要加行号"
- 不加的话，导出的 Excel 会多一列"空列"，用户看着奇怪

**`sheet_name="own_articles"` 是什么**：

- Excel 里 sheet 标签的名字
- 打开 xlsx 时底部会看到这个标签

**`output.seek(0)` 是什么**：

- `BytesIO` 就像一个文件，有"读写指针"
- 刚写完时，指针在末尾
- `seek(0)` 把指针移回开头
- 不 seek 的话，读取时会从"末尾"读，读到空

**关键点**：这一步不需要磁盘。全部在内存完成。

**和导入的区别**：导入是"读 Excel"（`pd.read_excel`），导出是"写 Excel"（`pd.ExcelWriter`）。方向相反，用的 API 不同。

---

### ⑤ → ⑦：BytesIO → StreamingResponse

**代码**：

```python
return StreamingResponse(
    output,
    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    headers={"Content-Disposition": "attachment; filename=own_articles_export.xlsx"}
)
```

**数据形态**：FastAPI 把 `output`（BytesIO）当成"文件流"，一边读一边发给前端。

**`media_type` 那串长字符串是什么**：

- `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` 是 xlsx 文件的标准 MIME 类型
- 浏览器看到这个类型，会识别成 Excel 文件

**`Content-Disposition` 是什么**：

- `attachment`：告诉浏览器"这是附件，触发下载"
- `filename=own_articles_export.xlsx`：告诉浏览器"下载时保存成这个文件名"

**关键点**：不是直接返回 `output`，而是用 `StreamingResponse` 包一层。这样 FastAPI 会把 BytesIO 当流处理，而不是一次性加载到内存。

**和导入的区别**：导入时前端**发**流给后端，导出时后端**发**流给前端。方向相反。

---

### ⑦ → ⑧：HTTP 响应 → 前端 blob

**代码**：

```javascript
const blob = await resp.blob();
```

**数据形态**：一个 `Blob` 对象，前端能操作的"二进制大对象"。

**关键点**：`resp.blob()` 是异步操作。要 `await`。

**为什么不用 `resp.json()`**：因为响应不是 JSON，是二进制。用 `blob()` 才对。

---

### ⑧ → ⑨：blob → 用户下载

**代码**：

```javascript
const url = window.URL.createObjectURL(blob);
const a = document.createElement("a");
a.href = url;
a.download = "own_articles_export.xlsx";
document.body.appendChild(a);
a.click();
document.body.removeChild(a);
window.URL.revokeObjectURL(url);
```

**逐行解释**：

| 行 | 作用 |
|---|---|
| `createObjectURL(blob)` | 给 blob 生成一个临时的 `blob://xxx` URL |
| `createElement("a")` | 造一个不可见的 `<a>` 标签 |
| `a.href = url` | 让 a 指向那个 blob URL |
| `a.download = "..."` | 告诉浏览器"点这个 a 就是下载这个文件，文件名是 xxx" |
| `appendChild(a)` | 把 a 加到页面（有些浏览器需要它出现在 DOM 里才触发下载） |
| `a.click()` | 模拟点击，触发下载 |
| `removeChild(a)` | 下载完删掉 a |
| `revokeObjectURL(url)` | 释放 blob URL（不释放会占内存） |

**关键点**：这套流程是**前端下载文件的固定套路**。所有"点按钮下载文件"的功能都这么写。记住就行。

---

### 完整转换表

| 阶段 | 数据形态 | 关键操作 | 契约 |
|---|---|---|---|
| ① | 数据库行 | SELECT | 列名 = SQL 里写的 |
| ② | 元组列表 | `fetchall()` | 顺序 = SELECT 顺序 |
| ③ | 列名列表 | `cur.description` | — |
| ④ | DataFrame | `pd.DataFrame(rows, columns=cols)` | 列数 = 行数匹配 |
| ⑤ | Excel 字节 | `pd.ExcelWriter` | sheet_name |
| ⑥ | BytesIO | `io.BytesIO()` | — |
| ⑦ | 响应流 | `StreamingResponse` | media_type, filename |
| ⑧ | 前端 blob | `resp.blob()` | — |
| ⑨ | 磁盘文件 | `a.click()` | 下载文件名 |

---

## 三处可能的改善点

### 改善点一：SQL 内联在 main.py

**现状**：SQL 直接写在路由函数里，没走 `content/own.py`。

**好处**：简单，少一层调用。

**坏处**：跟导入风格不统一（导入走 content 层）。

**要不要改**：暂时不用。等真的要统一风格时再挪。

### 改善点二：没有支持"按条件导出"

**现状**：每次导出都是**全表**（`SELECT ... FROM own_articles`，没有 WHERE）。

**用户场景**：如果以后想导出"最近 30 天"、"只导小红书平台"，现在做不到。

**要不要改**：看需求。如果未来要用，加一个 `WHERE` 条件参数就行。现在数据少，全表导出够用。

### 改善点三：没有行数上限

**现状**：全表导出，多少行都导。

**潜在问题**：如果表里有 10 万行，Excel 会有 10 万行，浏览器下载可能慢，Excel 打开也慢。

**要不要改**：现在不用担心。真到数据量大的时候再加 `LIMIT`。

---

## 一句话总结

> **导出 = 数据库行 → 元组列表 → DataFrame → Excel 字节 → BytesIO → 流式响应 → blob → 磁盘文件。**
>
> 比导入简单，因为**不调外部 API、不写临时文件、不转向量**。