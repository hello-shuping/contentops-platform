# 功能文档 · 导出爆文

> 状态：v1
> 最后更新：2026-10-01

---

## 第一节 · 代码地图

### 调用链路

```
【前端 · index.html】
  │
  ├─ 按钮
  │    <button onclick="downloadViral()">爆文库</button>
  │
  └─ 下载函数 downloadViral()
       │
       │  fetch("/export_viral_articles", {
       │      method: "GET",
       │      headers: {"X-Auth-Key": AUTH_KEY}
       │  })
       ▼
【路由层 · main.py】
  │
  └─ @app.get("/export_viral_articles")
     async def export_viral_articles(_: str = Depends(verify_key)):
       │
       ├─ 1. verify_key                    鉴权
       ├─ 2. 从连接池取连接
       ├─ 3. SELECT 查询 viral_articles
       ├─ 4. 取出行数据 + 列名
       ├─ 5. 构造 DataFrame
       ├─ 6. 写入 io.BytesIO（内存中的虚拟文件）
       └─ 7. StreamingResponse 返回二进制流
            ▼
【前端 · downloadViral()】
  │
  ├─ 收到 blob（二进制）
  ├─ 创建临时 <a> 标签
  ├─ 触发下载
  └─ 保存成 viral_articles_export.xlsx
```

### 涉及的函数与文件

| 位置 | 函数 | 说明 |
|---|---|---|
| index.html | `downloadViral()` | 发请求、接收 blob、触发下载 |
| main.py | `export_viral_articles` | 接口函数 |
| main.py | `verify_key` | 鉴权（被 Depends 调） |
| config.py | `pool` | 数据库连接池 |
| 外部 | 无 | 不调任何外部 API |

### 和"导出自己的文章"的差异

两个导出接口结构**完全一致**，只在三处不同：

| 差异点 | 导出自己的文章 | 导出爆文 |
|---|---|---|
| 查的表 | `own_articles` | `viral_articles` |
| 导出的字段 | 见下方 | 见下方 |
| sheet 名 / 文件名 | `own_articles` / `own_articles_export.xlsx` | `viral_articles` / `viral_articles_export.xlsx` |

**代码地图的逻辑一模一样**，只是 SQL 和文件名不同。

### 和导入的最大区别

**导出不调外部 API。**

- 导入：每条文章调一次千问 embedding 转向量
- 导出：只查库 + 生成 Excel + 返回

**所以导出快。** 1000 条数据也就 1-2 秒。

---

## 第二节 · 接口卡片

### 基本信息

| 项 | 内容 |
|---|---|
| 路径 | `/export_viral_articles` |
| 方法 | GET |
| 鉴权 | 需要 `X-Auth-Key` header |
| 触发方式 | 前端「爆文库」按钮 |
| 功能 | 从 `viral_articles` 表导出全部数据为 xlsx |

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
Content-Disposition: attachment; filename=viral_articles_export.xlsx
```

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
| viral_articles | 只读（SELECT） |

**导出不影响数据。** 表里的内容不会变。

### 导出字段

```
id, title, content, author, author_followers,
platform, note_url, likes, collects, comments, collected_date
```

**共 11 列。** 其中：

| 字段 | 含义 |
|---|---|
| author | 作者昵称 |
| author_followers | 作者粉丝数（红狐不返回，填 0） |
| note_url | 笔记原始链接 |
| collected_date | 采集日期（不是发布日期） |

**`embedding` 字段不导出**（1024 维向量，无意义且巨大）。

**`work_id` 字段也不导出**（去重用的内部键，不需要给用户看）。

### 和自己文章导出字段的对比

| 字段 | own_articles | viral_articles |
|---|---|---|
| id | ✅ | ✅ |
| title | ✅ | ✅ |
| content | ✅ | ✅ |
| platform | ✅ | ✅ |
| publish_date | ✅ | ❌ |
| collected_date | ❌ | ✅ |
| views | ✅ | ❌ |
| likes | ✅ | ✅ |
| collects | ✅ | ✅ |
| comments | ✅ | ✅ |
| shares | ✅ | ❌ |
| followers_gained | ✅ | ❌ |
| author | ❌ | ✅ |
| author_followers | ❌ | ✅ |
| note_url | ❌ | ✅ |

**共同字段**：`id`、`title`、`content`、`platform`、`likes`、`collects`、`comments`

**各自独有的**：自己文章有 `views`、`shares`、`followers_gained`、`publish_date`；爆文有 `author`、`author_followers`、`note_url`、`collected_date`

### 性能

| 规模 | 预估耗时 |
|---|---|
| 100 条 | < 1 秒 |
| 1000 条 | 1-2 秒 |

**不涉及任何外部 API 调用**，没有限流问题。

### 修改路径时需同步改

| 文件 | 位置 |
|---|---|
| index.html | `fetch("/export_viral_articles", ...)` |
| main.py | `@app.get("/export_viral_articles")` |

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

**和导出自己的文章完全一致。** 下面只讲和"自己的文章"不同的地方。

---

### ① → ②：数据库行 → Python 元组列表

**代码**：

```python
await cur.execute("""
    SELECT id, title, content, author, author_followers,
           platform, note_url, likes, collects, comments, collected_date
    FROM viral_articles
    ORDER BY id DESC
""")
rows = await cur.fetchall()
```

**数据形态**：

```python
[
    (1, "考研英语怎么学", "正文...", "考研英语酱", 0, "小红书",
     "https://...", 8500, 2400, 156, date(2026,9,20)),
    (2, "政治选择题技巧", "正文...", "考研政治老张", 0, "小红书",
     "https://...", 6200, 1800, 98, date(2026,9,19)),
    ...
]
```

**关键点**：

- `author_followers` 字段**永远是 0**——因为红狐 API 不返回作者粉丝数。这是字段存在但值为空的情况。
- `collected_date` 是采集日期，不是笔记发布日期。因为红狐返回的 `workPublishTime` 之前没存，只存了"采集时的日期"。
- `note_url` 是完整的 URL 字符串。

---

### ③ + ④ → ⑤：DataFrame → Excel 字节

**代码**：

```python
df = pd.DataFrame(rows, columns=cols)

output = io.BytesIO()
with pd.ExcelWriter(output, engine="openpyxl") as writer:
    df.to_excel(writer, index=False, sheet_name="viral_articles")
output.seek(0)
```

**和自己文章导出的唯一区别**：

- `sheet_name="viral_articles"`（自己文章是 `"own_articles"`）

其他代码一字不差。

---

### ⑤ → ⑦：BytesIO → StreamingResponse

**代码**：

```python
return StreamingResponse(
    output,
    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    headers={"Content-Disposition": "attachment; filename=viral_articles_export.xlsx"}
)
```

**和自己文章导出的唯一区别**：

- `filename=viral_articles_export.xlsx`（自己文章是 `own_articles_export.xlsx`）

`media_type` 完全一样——都是 xlsx 标准 MIME 类型。

---

### ⑦ → ⑨：前端下载

**代码**（在 `downloadViral` 里）：

```javascript
const blob = await resp.blob();
const url = window.URL.createObjectURL(blob);
const a = document.createElement("a");
a.href = url;
a.download = "viral_articles_export.xlsx";   // ← 唯一区别：文件名
document.body.appendChild(a);
a.click();
document.body.removeChild(a);
window.URL.revokeObjectURL(url);
```

**和自己文章导出的唯一区别**：

- `a.download = "viral_articles_export.xlsx"`

其他代码完全相同。

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

## 两处可能的改善点

### 改善点一：author_followers 永远是 0

**现状**：这个字段存在于表里，也导出了，但值永远是 0——因为红狐 API 不返回作者粉丝数。

**是不是问题**：对导出功能本身不是问题，导出的就是"表里是什么就是什么"。

**要不要处理**：两条路——要么删掉这一列（诚实点），要么留着（万一红狐以后加了字段）。现在留着。

### 改善点二：没有发布时间的字段

**现状**：导出的 `collected_date` 是"我采集数据的日期"，不是"笔记发布的时间"。

**为什么**：红狐 API 返回了 `workPublishTime`（笔记发布时间），但代码里**没存**。所以只能导出采集日期。

**要不要处理**：如果你做内容分析时想知道"这条爆文是什么时候发的"，需要先改 `save_viral_note` 把发布时间存下来。改完再改导出。

**这一条是真实的字段缺失，不只是"改善点"。** 时间维度对分析很重要。等你下次改数据层时一起处理。

---

## 一句话总结

> **导出爆文 = 导出自己的文章的"翻版"。**
>
> 结构完全一致，只是查的表、导出的字段、文件名不同。
>
> 两个接口的 SQL 和文件名一眼能看出差异，其他部分代码是复制的。