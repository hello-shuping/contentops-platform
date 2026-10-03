# content/analysis_viral_title.py
# 爆文标题特征归因分析
# 跑法：python content/analysis_viral_title.py

# ========== 第 0 步：导入依赖 ==========
import asyncio          # 异步运行（要 await 数据库）
import json             # 处理 JSON（LLM 返回 + 写文件）
import os               # 处理文件路径
import statistics       # 算中位数
import sys              # 处理 import 搜索路径
from datetime import datetime  # 取当前时间

# 把项目根目录加到 import 搜索路径，否则找不到 config
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from openai import OpenAI   # LLM 客户端
from config import config, pool   # 配置 + 数据库连接池


# ========== 第 1 步：全局对象和常量 ==========

# 1.1 创建 LLM 客户端（全脚本共用一个）
llm = OpenAI(api_key=config.API_KEY, base_url=config.BASE_URL)

# 1.2 输出文件路径：content/viral_title_patterns.json
OUTPUT_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "viral_title_patterns.json"
)

# 1.3 编码手册（写死的字符串，会拼进 LLM 的 prompt）
CODING_MANUAL = """你是内容分析编码员，请严格按以下定义给每条标题打标。

【has_number：标题是否含数字】
只算"数量词"：表示"几个 / 几步 / 几种"的数字。
不算：
- 年份、月份、日期："2027考研""9月刚开政治""27届"
- 序数："第3课""第二个方法"
- 泛指："一篇文章""十分有用"

正例："3个方法搞定考研英语"、"用5步拆解长难句"
反例："2027考研报名时间定了"、"9月刚开始考研"、"第3课笔记"

【has_pain：标题是否点出痛点】
只算直接点出具体困境的标题。
不算：
- 疑问句："怎么学""咋办""要不要"
- 泛话题："考研英语方法"

正例："背单词总是忘怎么办"、"刷题没效率的3个原因"
反例："考研英语学习方法"、"9月刚开政治咋学"、"关于考研数学，你们怎么看"

【has_trend：标题是否蹭热点】
蹭到近3个月的公共事件、政策、流行语。
正例："deepseek时代考研还有必要吗"
反例："考研英语长难句解析"（永恒话题）

【emotion：情绪浓度】
0 = 纯陈述（考研英语真题解析）
1 = 轻微倾向 / 疑问（要不要报班）
2 = 强烈情绪（崩溃就在一瞬间）
"""


# ========== 第 2 步：从数据库拉爆文数据 ==========
async def fetch_data():
    # 2.1 从连接池取连接，再取游标
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            # 2.2 执行 SQL：查标题 + 三个互动字段
            #     过滤空标题（空标题没法分析）
            await cur.execute("""
                SELECT title, likes, collects, comments
                FROM viral_articles
                WHERE title IS NOT NULL AND title != ''
            """)
            # 2.3 一次取出所有行
            rows = await cur.fetchall()

    # 2.4 逐行处理：算"互动量 = 点赞 + 收藏 + 评论"
    data = []
    for title, likes, collects, comments in rows:
        # (likes or 0) 是防御：likes 为 None 时取 0，避免 TypeError
        total = (likes or 0) + (collects or 0) + (comments or 0)
        data.append({"title": title, "score": total})

    # 2.5 返回：[{"title": "...", "score": 1234}, ...]
    return data


# ========== 第 3 步：让 LLM 给一批标题打标 ==========
def label_batch(titles):
    # 3.1 把标题列表变成"编号 + 标题"，给 LLM 用来对应
    numbered = "\n".join([f"{i}. {t}" for i, t in enumerate(titles)])

    # 3.2 拼 prompt：编码手册 + 标题列表 + 输出要求
    prompt = f"""{CODING_MANUAL}

【标题列表】
{numbered}

【输出要求】
只返回 JSON 数组，格式：
[{{"index": 0, "has_number": true, "has_pain": false, "has_trend": false, "emotion": 1}}, ...]
不要 markdown 代码块，不要解释。
"""

    # 3.3 调 LLM（temperature=0 保证输出稳定）
    resp = llm.chat.completions.create(
        model=config.MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )

    # 3.4 取出文本
    raw = resp.choices[0].message.content.strip()

    # 3.5 去掉可能的 markdown 代码块包裹
    raw = raw.replace("```json", "").replace("```", "").strip()

    # 3.6 JSON 字符串 → Python 列表，返回
    return json.loads(raw)


# ========== 第 4 步：算每个特征的 lift ==========
def calc_lift(data):
    """按特征分组，用中位数算 lift（中位数对极端值稳健）"""

    # 4.1 三个二值特征（emotion 是三分类，下面单独处理）
    features = ["has_number", "has_pain", "has_trend"]
    results = []

    # 4.2 逐个特征算
    for feat in features:
        # 4.2.1 分组：这个特征为 true 的组，为 false 的组
        with_feat = [d["score"] for d in data if d["labels"].get(feat)]
        without_feat = [d["score"] for d in data if not d["labels"].get(feat)]

        # 4.2.2 样本量门槛：任意一组少于 10 条，跳过
        if len(with_feat) < 10 or len(without_feat) < 10:
            continue

        # 4.2.3 算中位数（用中位数不用均值，躲开极端值）
        med_with = statistics.median(with_feat)
        med_without = statistics.median(without_feat)

        # 4.2.4 防除零
        if med_without == 0:
            continue

        # 4.2.5 算 lift = 有特征的中位数 / 无特征的中位数
        lift = med_with / med_without

        # 4.2.6 结果装进列表
        results.append({
            "feature": feat,
            "median_with": round(med_with, 2),
            "median_without": round(med_without, 2),
            "lift": round(lift, 2),
            "count_with": len(with_feat),
            "count_without": len(without_feat),
        })

    # 4.3 情绪单独处理（三分类 0/1/2）
    for level in [0, 1, 2]:
        # 4.3.1 取这一级的样本
        group = [d["score"] for d in data if d["labels"].get("emotion") == level]

        # 4.3.2 样本量门槛
        if len(group) < 10:
            continue

        # 4.3.3 算中位数
        med = statistics.median(group)

        # 4.3.4 没有对照组，lift 和 median_without 都是 None
        results.append({
            "feature": f"emotion_{level}",
            "median_with": round(med, 2),
            "median_without": None,
            "lift": None,
            "count_with": len(group),
            "count_without": None,
        })

    return results


# ========== 第 5 步：主流程 ==========
async def main():
    # 5.1 打开连接池（脚本独立运行，必须手动打开）
    await pool.open()
    try:
        # 5.2 拉数据
        print("读取爆文...")
        data = await fetch_data()
        print(f"共 {len(data)} 条")

        # 5.3 样本量门槛：少于 30 条直接退出
        if len(data) < 30:
            print("样本太少（<30 条），先爬一批再来")
            return

        # 5.4 抽出所有标题
        titles = [d["title"] for d in data]

        # 5.5 分批打标（每批 20 条）
        print("开始打标...")
        all_labels = []
        batch_size = 20
        for i in range(0, len(titles), batch_size):
            batch = titles[i:i + batch_size]

            # 5.5.1 调 LLM 打这一批
            labels = label_batch(batch)

            # 5.5.2 关键：把批内编号偏移成全局编号
            for item in labels:
                item["index"] = item["index"] + i

            all_labels.extend(labels)
            print(f"  已完成 {min(i + batch_size, len(titles))}/{len(titles)}")

        # 5.6 把标签挂回原数据
        label_map = {item["index"]: item for item in all_labels}
        for i, d in enumerate(data):
            d["labels"] = label_map.get(i, {})   # 兜底：没标到就空字典

        # 5.7 算 lift
        print("计算 lift...")
        patterns = calc_lift(data)

        # 5.8 组装输出
        output = {
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "sample_size": len(data),
            "metric": "median of (likes + collects + comments)",
            "patterns": patterns,
        }

        # 5.9 写文件
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

        # 5.10 打印结果到终端
        print(f"\n✅ 已写入 {OUTPUT_PATH}")
        print(f"\n【分析结果】（样本 {len(data)} 条，指标：中位数）")
        for p in patterns:
            if p["lift"] is not None:
                print(f"  {p['feature']:15} lift={p['lift']:.2f}  "
                      f"(有 {p['median_with']} / 无 {p['median_without']}, "
                      f"样本 {p['count_with']}/{p['count_without']})")
            else:
                print(f"  {p['feature']:15} 中位数 {p['median_with']}  (样本 {p['count_with']})")

    finally:
        # 5.11 无论成功失败，关闭连接池
        await pool.close()


# ========== 第 6 步：脚本入口 ==========
if __name__ == "__main__":
    # 只有直接运行这个文件才执行 main
    # 被别的文件 import 时不执行
    asyncio.run(main())