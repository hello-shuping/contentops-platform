# 导入爆文 · 设计说明

## 功能定位

把手动采集 / 外部爬取的小红书爆文数据，通过 Excel 批量导入 `viral_articles` 表。

**数据来源不限**：手动刷、开源爬虫、红狐 API——只要整理成 Excel，都从这里进。

**和"导入自己的文章"的区别**：
- 导入自己的文章：**全量覆盖**（Excel 是快照）
- 导入爆文：**增量累加**（Excel 是批次）

## 数据流

```
Excel 文件
  ↓ 前端点击"导入爆文"按钮
HTTP POST /import_viral_articles
  ↓ 文件写入临时文件
content/viral.py · import_from_excel_viral()
  ↓ 逐行处理
  ├─ 读取字段（title / content / publish_time / likes / collects / comments / followers）
  ├─ 解析发布时间标签（2m → 日期）
  ├─ 生成 work_id（标题的 md5 前 16 位 + manual_ 前缀）
  ├─ 调千问 embedding（标题 + 正文 → 1024 维向量）
  └─ INSERT（ON CONFLICT work_id DO NOTHING）
  ↓ 返回统计
前端显示"导入成功：X/Y 条（跳过 Z 条）"
```

## Excel 格式要求

**七列，表头必须完全一致**：

| 列名 | 含义 | 必填 | 示例 |
|---|---|---|---|
| `title` | 标题原文 | ✅ | `INFP的频繁离职，就是一场巨大的均值回归。` |
| `content` | 正文 | 否 | 全文（可空） |
| `publish_time` | 发布时间标签 | 否 | `2m` / `3d` / `1w` |
| `likes` | 点赞数 | 是 | `1663` |
| `collects` | 收藏数 | 是 | `715` |
| `comments` | 评论数 | 是 | `209` |
| `followers` | 作者粉丝数 | 否 | `1751` |

### publish_time 标签规则

| 小红书显示 | 填 |
|---|---|
| 3 天前 | `3d` |
| 2 周前 | `2w` |
| 1 个月前 | `1m` |

代码解析：
- `Nd` → 今天减 N 天
- `Nw` → 今天减 N 周
- `Nm` → 今天减 N × 30 天

解析结果存进 `publish_date` 字段。

## 去重机制

**work_id = `manual_` + 标题的 md5 前 16 位。**

作用：
- 同一个标题只插一次
- 重复导入同一份 Excel，不会翻倍
- **标题改一个字，work_id 就变**，会被当成新数据

**所以采集时标题要抄准，别手动改。**

## 字段缺失的处理

| 列 | 缺失时 |
|---|---|
| `title` | **整行跳过**（work_id 没法算） |
| `content` | 存空字符串 |
| `publish_time` | `publish_date` 存 NULL |
| `likes` / `collects` / `comments` | 存 0 |
| `followers` | 存 0 |

**只有 `title` 是硬门槛。** 其他缺了能进，但会影响分析质量，**尽量填全**。

## 性能

| 规模 | 耗时 |
|---|---|
| 15 条 | 约 10 秒 |
| 50 条 | 约 30 秒 |
| 100 条 | 约 1 分钟 |

**每条调一次 embedding API**，代码里有 `asyncio.sleep(0.5)` 防限流。

## 代码位置

| 位置 | 内容 |
|---|---|
| `index.html` | "导入爆文"按钮 + `uploadViral()` 函数 |
| `main.py` | `/import_viral_articles` 接口 |
| `content/viral.py` | `import_from_excel_viral()` 函数 |
| 外部依赖 | 千问 embedding API |

## 数据去向

导入后，数据进 `viral_articles` 表。

**被三个地方使用**：

| 用途 | 谁在用 |
|---|---|
| 向量检索参考 | `generate_title` / `write_article` |
| 数据分析 | `analysis/analysis_viral_title.py` |
| 原创度检测 | `check_originality`（作为候选库） |

## 未来待做的优化

1. **导出后能再导入**（目前导出字段和导入字段不完全一致，缺逆向映射）
2. **导入日志落盘**（现在只在终端打印，没存记录）
3. **错误行明细返回**（现在只返回统计数字，不知道哪些行失败了）