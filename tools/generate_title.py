# tools/generate_title.py
# 生成标题

import json
import os
from content.viral import search_viral_articles


def load_title_report():
    """读取行业知识版标题报告（analysis/title_report.md）"""
    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "analysis",
        "title_report.md",
    )
    if not os.path.exists(path):
        return ""

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    return f"\n【标题写作指南】\n{content}\n"


def load_emotion_rule():
    """读取数据版标题规律（analysis/viral_title_patterns.json）"""
    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "analysis",
        "viral_title_patterns.json",
    )
    if not os.path.exists(path):
        return ""

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    lines = []
    for p in data.get("patterns", []):
        lift = p.get("lift")
        delta = p.get("cliffs_delta")

        # 采纳条件：lift > 1.2 且 |delta| > 0.15 且两组样本都 ≥ 15
        if lift is None or delta is None:
            continue
        if (lift > 1.2 and abs(delta) > 0.15
                and p.get("count_with", 0) >= 15
                and p.get("count_without", 0) >= 15):
            lines.append(
                f"- {p['feature']}：lift={lift}，"
                f"样本 {p['count_with']}/{p['count_without']}（效应量 δ={delta}）"
            )

    if not lines:
        return ""

    return (
        f"\n【数据实证规律（基于 {data['sample_size']} 条爆文）】\n"
        + "\n".join(lines)
        + "\n建议生成时优先体现上述特征。\n"
    )


async def generate_title(topic: str, count: int = 5, style: str = "干货型") -> str:
    style_map = {
        "干货型": "直接给价值点，如'3个方法''避坑指南''从0到1'，一眼看出能得到什么",
        "轻松型": "口语化，像朋友分享，带情绪和好奇心",
        "故事感": "用悬念、冲突或反差开头，让人想点进去看后续",
        "种草型": "以个人真实体验口吻推荐方法和经验，不引入具体商品",
    }
    current_rules = style_map.get(style, style_map["干货型"])

    similar = await search_viral_articles(topic, limit=5)
    if similar:
        reference = "\n".join([f"- {a['title']}" for a in similar if a['title']])
        reference_block = f"\n参考这些爆款标题的风格：\n{reference}\n"
    else:
        reference_block = ""

    report_block = load_title_report()
    rule_block = load_emotion_rule()

    return f"""生成 {count} 个「{style}」风格标题，主题：{topic}。

规则：{current_rules}
{reference_block}
{report_block}
{rule_block}
只输出标题，每行一个，不要解释。"""