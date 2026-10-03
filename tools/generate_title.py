# tools/generate_title.py
# 生成标题

import json
import os
from content.viral import search_viral_articles


def load_emotion_rule():
    """读取 viral_title_patterns.json 里的情绪规律"""
    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "content",
        "viral_title_patterns.json",
    )
    if not os.path.exists(path):
        return ""

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    rules = []
    for p in data.get("patterns", []):
        if p["feature"].startswith("emotion_") and p.get("median_with"):
            rules.append(f"情绪浓度{p['feature'][-1]}（中位数 {p['median_with']}）")

    if not rules:
        return ""

    return f"""
【爆款数据规律】
根据 {data.get('sample_size', 0)} 条爆文统计，标题情绪浓度越高，互动量越高：
{chr(10).join(rules)}
请在生成时给标题加入情绪，但不要用电商式喊话（如"救命""谁懂啊""速抢"）。
情绪可以来自：贴近考研人真实处境的表达、口语化的感叹、说到心坎里的共鸣感。
"""


async def generate_title(topic: str, count: int = 5, style: str = "干货型") -> str:
    style_map = {
        "干货型": "直接给价值点，如'3个方法''避坑指南''从0到1'，一眼看出能得到什么，可带1个Emoji",
        "轻松型": "口语化，像闺蜜分享，带情绪和好奇心，可带1个Emoji",
        "故事感": "用悬念、冲突或反差开头，让人想点进去看后续，可带1个Emoji",
        "种草型": "以个人真实体验口吻推荐方法和经验（不引入具体商品），像跟朋友安利一个有用的思路，可带1个Emoji",
    }
    current_rules = style_map.get(style, style_map["干货型"])

    similar = await search_viral_articles(topic, limit=5)
    if similar:
        reference = "\n".join([f"- {a['title']}" for a in similar if a['title']])
        reference_block = f"\n参考这些爆款标题的风格：\n{reference}\n"
    else:
        reference_block = ""

    emotion_block = load_emotion_rule()

    return f"""生成 {count} 个「{style}」风格标题，主题：{topic}。

规则：{current_rules}
{reference_block}
{emotion_block}
只输出标题，每行一个，不要解释。"""