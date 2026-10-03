# tools/write_article.py
# 撰写文章

from content.viral import search_viral_articles


async def write_article(topic: str, word_count: int = 1200, style: str = "正式") -> str:
    style_map = {
        "正式": "语言严谨，逻辑清晰，适合职场阅读",
        "轻松": "语言活泼，像朋友聊天，读起来不累",
        "专业": "使用行业术语，有深度分析，适合专业人士",
        "故事感": "用故事开头，有细节描写，有代入感",
        "口语化": "像跟朋友聊天一样，少用书面语，多举具体例子，语气自然",
    }
    style_desc = style_map.get(style, style_map["正式"])

    similar = await search_viral_articles(topic, limit=3)
    if similar:
        reference = "\n\n".join([
            f"【{a['title']}】\n{a['content'][:200]}..."
            for a in similar if a['title']
        ])
        reference_block = f"\n参考这些爆款文章的结构和风格：\n{reference}\n"
    else:
        reference_block = ""

    return f"""请根据以下主题写一篇文章：
主题：{topic}
目标字数：约{word_count}字，上下浮动不超过10%。
风格要求：{style_desc}
{reference_block}
结构要求：
1. 开头：吸引人，引出主题
2. 正文：分3-5个小节，逻辑清晰
3. 结尾：总结观点或行动建议
只输出文章正文，不要加额外说明。"""