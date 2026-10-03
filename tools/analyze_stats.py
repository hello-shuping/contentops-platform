# tools/analyze_stats.py

from content.own import get_stats_summary


async def analyze_stats(platform: str = "小红书") -> str:
    data = await get_stats_summary(platform if platform else None)

    if not data:
        return "请直接回复用户：当前没有可分析的文章数据，请先在页面右上角导入 Excel。"

    lines = []
    for row in data[:20]:
        lines.append(
            f"{row['title']} | 互动率 {row['互动率']}% | 收藏率 {row['收藏率']}%"
        )

    return (
        "以下是用户文章的数据表现：\n"
        + "\n".join(lines)
        + "\n\n请分析哪类内容效果好，给出简短的创作建议。"
    )