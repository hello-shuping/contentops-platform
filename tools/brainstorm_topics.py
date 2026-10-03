# tools/brainstorm_topics.py
# 批量专题策划

from content.viral import search_viral_articles


async def brainstorm_topics(topic: str, goals: list = None, count: int = 5) -> str:
    if goals is None:
        goals = ["涨粉", "转化", "引流", "互动"]

    similar = await search_viral_articles(topic, limit=10)
    if similar:
        reference = "\n".join([f"- {a['title']}" for a in similar if a['title']])
        reference_block = f"\n参考这些爆款方向：\n{reference}\n"
    else:
        reference_block = ""

    goals_str = "、".join(goals)

    return f"""请围绕「{topic}」这个领域，按以下目标各策划 {count} 个专题：

目标类型：{goals_str}
{reference_block}
要求：
- 专题是系列级的，一个专题下面能延伸出多篇内容，不是单篇文章的题目
- 每个目标下的专题要有明显区分
- 每个专题写清楚：讲什么、包含哪些方向

输出格式：

【涨粉】
1. 专题名称
   讲什么：xxx
   包含：方向1、方向2、方向3

【转化】
1. 专题名称
   讲什么：xxx
   包含：方向1、方向2、方向3

只输出专题清单，不要解释。"""