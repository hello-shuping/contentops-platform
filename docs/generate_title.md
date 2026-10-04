# 生成标题 · 设计说明

## 三层支撑结构

`generate_title` 的 prompt 由三层内容拼成：

| 层级 | 来源 | 状态 |
|---|---|---|
| ① 爆文样本 | `search_viral_articles()` 检索 5 条相关爆文 | ✅ 生效 |
| ② 行业知识报告 | `analysis/title_report.md` | ✅ 生效 |
| ③ 数据实证规则 | `analysis/viral_title_patterns.json` | ⚠️ 管道就绪，数据待补 |

## 三层的作用

**① 爆文样本**

每次生成时，按主题检索 5 条最相似的爆文标题，让 LLM 参考风格。
库越大、输入越具体，检索越精准。

**② 行业知识报告**

内容行业通用规律 + INFP 领域观察。
包含：标题长度、四种结构、情绪浓度、句式模板、优先级。
**永远生效**，不依赖数据。

**③ 数据实证规则**

从 `viral_articles` 跑分析出来的统计规律。
**采纳门槛**：lift > 1.2、|Cliff's delta| > 0.15、两组样本都 ≥ 15。
当前 39 条数据，分组后样本不足，规则未被采纳。
等数据到 80-100 条，重新跑分析，规则会自动生效。

## 输入建议

**输入越具体，生成质量越高。**

| 输入 | 效果 |
|---|---|
| "INFP" | 偏泛，输出偏方法论 |
| "INFP 内耗" | 检索到更精准的爆文，输出质量明显提升 |
| "INFP 职场，故事感" | 主题 + 风格都明确，输出最锐利 |

**推荐格式**：

```
生成3个「具体问题」的 INFP 标题，风格
```

## 代码位置

- 生成逻辑：`tools/generate_title.py`
- 行业报告：`analysis/title_report.md`
- 数据规则：`analysis/viral_title_patterns.json`
- 分析脚本：`analysis/analysis_viral_title.py`