# analysis/analysis_viral_title.py
# 爆文标题特征归因分析（精简版：2 个特征 + 非参数检验）
# 跑法：python analysis/analysis_viral_title.py

# ========== 第 0 步：导入依赖 ==========
import asyncio
import json
import os
import statistics
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from openai import OpenAI
from scipy import stats

from config import config, pool


# ========== 第 1 步：全局对象和常量 ==========
llm = OpenAI(api_key=config.API_KEY, base_url=config.BASE_URL)

OUTPUT_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "viral_title_patterns.json"
)

# 只留 2 个特征
CODING_MANUAL = """你是内容分析编码员，请严格按以下定义给每条标题打标。

【has_contrast：标题是否有反差】
标题里存在两个对立 / 冲突的元素，制造张力。

三种形式：
- 认知反差："以为 A，其实 B"、"看起来 X，实际上 Y"
- 人群反差："XX 人却 XX 样"
- 类型反差："A 型最像 B 型"

正例："为什么 INFP 看着犹豫，却很难被说服"、"INFP 的本质就是自私冷漠"
反例："INFP 的怀疑，往往就是事实"（纯陈述）、"INFP 上班的尽头是抑郁吗？"（疑问句）

不算：
- 单纯情绪化吐槽（"INFP 好难"）
- 单纯疑问（"INFP 怎么办"）
- 单纯陈述（"INFP 的日常"）

边界：
- 反驳刻板印象算 true（"INFP 不是内向，是深度社交"）
- 只出现一个元素（哪怕很强）不算

【is_experience：标题是否是个人经验分享】

1 = 个人经验分享
   第一人称，讲自己的经历 / 故事 / 观察 / 感受。
   特征词："我""自己""作为 INFP 我……""最近""发现"。
   例：
   - "gap 半年后我才明白……"
   - "一直以为自己只是在拖延……"
   - "我不认可 INFP 爱摆烂"
   - "经常性倾诉 我本人是那种……"
   - "感觉 INFP 真三分钟热度……"

0 = 非个人经验
   第三人称，讲概念 / 分析 / 科普 / 清单 / 观察他人。
   特征：主语是"INFP"群体，不是"我"。
   例：
   - "INFP 的 5 个典型特征"
   - "infp 最应该学习的人是苏三多"
   - "INFP 小蝴蝶的隐藏天赋"
   - "为什么 INFP 工作总是不稳定"（疑问句，无第一人称）
   - "INFP 所谓的低阶其实是大佬幼年体"（分析性论断）

边界：
   - "作为 INFP 我认为 X 是 Y" → 有"我"，但如果后面是观点而非经历 → 0
   - "我身边的 INFP 都是……" → 讲别人，不是讲自己 → 0
   - "我发现 INFP 都……" → 有"我"但是总结群体 → 0
"""


# ========== 第 2 步：从数据库拉爆文数据 ==========
async def fetch_data():
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                SELECT title, likes, collects, comments
                FROM viral_articles
                WHERE title IS NOT NULL AND title != ''
            """)
            rows = await cur.fetchall()

    data = []
    for title, likes, collects, comments in rows:
        total = (likes or 0) + (collects or 0) + (comments or 0)
        data.append({"title": title, "score": total})
    return data


# ========== 第 3 步：让 LLM 给一批标题打标 ==========
def label_batch(titles):
    numbered = "\n".join([f"{i}. {t}" for i, t in enumerate(titles)])

    prompt = f"""{CODING_MANUAL}

【标题列表】
{numbered}

【输出要求】
只返回 JSON 数组，格式：
[{{"index": 0, "has_contrast": false, "is_experience": true}}, ...]
不要 markdown 代码块，不要解释。
"""

    resp = llm.chat.completions.create(
        model=config.MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    raw = resp.choices[0].message.content.strip()
    raw = raw.replace("```json", "").replace("```", "").strip()
    labels = json.loads(raw)

    returned = {item["index"] for item in labels}
    for i in range(len(titles)):
        if i not in returned:
            labels.append({
                "index": i,
                "has_contrast": None,
                "is_experience": None,
            })
    return labels


# ========== 第 4 步：算 lift + 非参数检验 ==========
def calc_lift(data):
    """按特征分组：算 lift、Mann-Whitney U 检验、Cliff's delta 效应量"""

    # 排除超级爆款（互动量 > 10000）
    OUTLIER_LIMIT = 10000
    original_count = len(data)
    data = [d for d in data if d["score"] <= OUTLIER_LIMIT]
    excluded = original_count - len(data)
    if excluded > 0:
        print(f"  （排除 {excluded} 条超级爆款，互动量 > {OUTLIER_LIMIT}）")

    features = ["has_contrast", "is_experience"]
    results = []

    for feat in features:
        with_feat = [d["score"] for d in data if d["labels"].get(feat)]
        without_feat = [d["score"] for d in data if not d["labels"].get(feat)]

        if len(with_feat) < 10 or len(without_feat) < 10:
            print(f"  （跳过 {feat}：样本不足，{len(with_feat)}/{len(without_feat)}）")
            continue

        # lift
        med_with = statistics.median(with_feat)
        med_without = statistics.median(without_feat)
        if med_without == 0:
            continue
        lift = med_with / med_without

        # Mann-Whitney U 检验
        try:
            u_stat, p_value = stats.mannwhitneyu(
                with_feat, without_feat, alternative="two-sided"
            )
            n1, n2 = len(with_feat), len(without_feat)
            cliffs_delta = (2 * u_stat) / (n1 * n2) - 1
        except Exception as e:
            p_value = None
            cliffs_delta = None

        results.append({
            "feature": feat,
            "median_with": round(med_with, 2),
            "median_without": round(med_without, 2),
            "lift": round(lift, 2),
            "p_value": round(p_value, 4) if p_value is not None else None,
            "cliffs_delta": round(cliffs_delta, 3) if cliffs_delta is not None else None,
            "count_with": len(with_feat),
            "count_without": len(without_feat),
        })

    return results


# ========== 第 5 步：主流程 ==========
async def main():
    await pool.open()
    try:
        print("读取爆文...")
        data = await fetch_data()
        print(f"共 {len(data)} 条")

        if len(data) < 30:
            print("样本太少（<30 条），先采一批再来")
            return

        titles = [d["title"] for d in data]

        print("开始打标...")
        all_labels = []
        batch_size = 20
        for i in range(0, len(titles), batch_size):
            batch = titles[i:i + batch_size]
            labels = label_batch(batch)
            for item in labels:
                item["index"] = item["index"] + i
            all_labels.extend(labels)
            print(f"  已完成 {min(i + batch_size, len(titles))}/{len(titles)}")

        label_map = {item["index"]: item for item in all_labels}
        for i, d in enumerate(data):
            d["labels"] = label_map.get(i, {})

        print("计算 lift + 非参数检验...")
        patterns = calc_lift(data)

        output = {
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "sample_size": len(data),
            "metric": "median of (likes + collects + comments)",
            "patterns": patterns,
        }

        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

        print(f"\n✅ 已写入 {OUTPUT_PATH}")
        print(f"\n【分析结果】（样本 {len(data)} 条，指标：中位数）")
        print(f"{'特征':<16} {'lift':>6} {'p值':>8} {'效应量':>10} {'样本':>10}")
        print("-" * 58)

        for p in patterns:
            feat = p["feature"]
            lift = f"{p['lift']:.2f}" if p.get("lift") is not None else "—"
            pval = f"{p['p_value']:.4f}" if p.get("p_value") is not None else "—"
            if p.get("cliffs_delta") is not None:
                eff = f"δ={p['cliffs_delta']:.2f}"
            else:
                eff = "—"
            counts = f"{p['count_with']}/{p['count_without']}"
            print(f"{feat:<16} {lift:>6} {pval:>8} {eff:>10} {counts:>10}")

        print("\n判读参考：")
        print("  Cliff's delta: <0.15 可忽略 | 0.15-0.33 小 | 0.33-0.47 中 | >0.47 大")
        print("  p < 0.05 → 差异显著（样本小时 p 值容易不显著，看 lift 和 δ 更有信息量）")

    finally:
        await pool.close()


# ========== 第 6 步：脚本入口 ==========
if __name__ == "__main__":
    asyncio.run(main())