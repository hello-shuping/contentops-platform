# content/kappa_check.py
# 黄金标准校准：人工标 vs LLM 标，算 Kappa
# 目的：验证 LLM 打标的可信度
# 跑法：python content/kappa_check.py

# ========== 第 0 步：导入依赖 ==========
import asyncio              # 异步运行（要 await 数据库）
import json                 # 处理 JSON（解析 LLM 返回 + 读人工标文件）
import os                   # 处理文件路径
import sys                  # 处理 import 搜索路径

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from openai import OpenAI
from sklearn.metrics import cohen_kappa_score

from config import config, pool


# 创建 LLM 客户端（全脚本共用一个）
llm = OpenAI(api_key=config.API_KEY, base_url=config.BASE_URL)


# ========== 第 1 步：从独立文件读人工标（黄金标准） ==========
# 人工标不再硬编码在代码里，而是放在 golden_standard.json
# 好处：加新样本不用改代码，直接改 JSON
GOLDEN_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "golden_standard.json"
)

with open(GOLDEN_PATH, "r", encoding="utf-8") as f:
    _golden = json.load(f)

# 转成 {id: 标签字典} 的形式，方便后续查询
HUMAN_LABELS = {item["id"]: item["human"] for item in _golden["samples"]}


# ========== 第 2 步：编码手册 ==========
CODING_MANUAL = """你是内容分析编码员，请严格按以下定义给每条标题打标。

【has_number：标题是否含数字】
只算"数量词"：表示"几个 / 几步 / 几种"的数字。
不算：
- 年份、月份、日期："2026 年 INFP 运势""9 月 INFP 状态"
- 序数："INFP 的第二种类型""第 3 种 INFP"
- 泛指："INFP 的一些特征""十分典型的 INFP"

正例："3 个迹象说明你是 INFP"、"INFP 的 5 个典型特征"
反例："2026 年 INFP 运势"、"9 月 INFP 状态"、"INFP 的第二种类型"

【has_pain：标题是否戳中 INFP 群体的真实困境】
判断标准：这条标题 INFP 看了会不会被"戳中"（内心有共鸣、隐隐作痛）。

INFP 的典型痛点类型：
① 自我认知冲突
   别人以为我是 A，其实我是 B。
   例："INFP 的本质就是自私冷漠"（反驳"温柔善良"的刻板印象）
       "INTJ 其实在青年时期最佩服的人是 INFP"（意外性认同）

② 社会化困境
   在适应社会 / 职场过程中感到疲惫。
   例："INFP 的频繁离职"、"INFP 的社会化就是不断黑化吗"
       "INFP 上班的尽头是抑郁吗"、"INFP 工作总是不稳定"

③ 自我否定 / 自我怀疑
   对自己价值、性格的负面评价。
   例："INFP 最难发现的问题可能是 Fi 滋生的大 Ego"
       "INFP 最大的缺点：自我意识过强"

④ 关系困境
   与人相处中的疲惫、不解、冲突。
   例："为什么 INFP 看着犹豫，却很难被说服"

算 true：
- 提到 INFP 的负面特质（贬义词，如"自私""冷漠""大 Ego""黑化"）
- 提到 INFP 遇到的困境（"离职""崩溃""抑郁""不稳定""难"）
- 提到 INFP 与外界 / 自我的冲突（"看着 X 却 Y"、"别人以为 X 其实 Y"）

算 false：
- 中性描述："INFP 的日常""INFP 是什么""ENFP 眼里的 INFP"
- 纯好奇 / 疑问："INFP 适合什么工作""INFP 应该怎么改变"
- 正面评价："INFP 很可爱""INFP 是理想型"
- 好奇型互动："感觉 INFP 出小狗的概率比别的 MBTI 高"

边界情况：
- "其实我觉得 INFP 最适合干服务行业" → false（观点表达，不是困境）
- "INFP 成为高阶的第一步就是解除性缘脑" → true（点出 INFP 的认知盲区）
- "INFP 的怀疑，往往就是事实" → true（点出 INFP 的内在冲突：敏感 / 直觉）
- "INFP 到底应该怎么样，性格才会产生巨变" → true（隐含"现在的 INFP 有问题"）

【has_trend：标题是否蹭热点】
蹭到近 3 个月的公共事件、政策、流行语。
正例："DeepSeek 爆火后，INFP 的职场还有出路吗"
反例："INFP 的 5 个典型特征"（永恒话题）

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

【emotion：标题是否有情感波动（二分类）】

1 = 有情感波动
   读起来能感觉到情绪起伏、张力、反差、或强断言。
   例：
   - "INFP 的本质就是自私冷漠"（反差 + 强判断）
   - "INTJ 其实最佩服 INFP"（反常 + 褒义）
   - "INFP 的怀疑，往往就是事实"（推翻刻板印象，带情绪）
   - "INFP 上班的尽头是抑郁"（强贬义）

0 = 平静描述 / 平缓表达
   读起来是观察、分析、陈述，没有情绪起伏。
   例：
   - "其实我觉得 INFP 最适合干服务行业"（平静的自我剖析）
   - "INFP 最大的缺点：自我意识过强"（客观分析）
   - "ENFP 眼里的 INFP"（中性描述）
   - "INFP 是什么"（中性）
"""


# ========== 第 3 步：让 LLM 给一批标题打标 ==========
def label_batch(titles):
    numbered = "\n".join([f"{i}. {t}" for i, t in enumerate(titles)])

    prompt = f"""{CODING_MANUAL}

【标题列表】
{numbered}

【输出要求】
只返回 JSON 数组，格式：
[{{"index": 0, "has_number": true, "has_pain": false, "has_trend": false, "has_contrast": false, "emotion": 1}}, ...]
emotion 只能是 0 或 1。不要 markdown 代码块，不要解释。
"""

    resp = llm.chat.completions.create(
        model=config.MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    raw = resp.choices[0].message.content.strip()
    raw = raw.replace("```json", "").replace("```", "").strip()
    labels = json.loads(raw)

    # 兜底：漏标就补个全 None 的
    returned = {item["index"] for item in labels}
    for i in range(len(titles)):
        if i not in returned:
            labels.append({
                "index": i,
                "has_number": None,
                "has_pain": None,
                "has_trend": None,
                "has_contrast": None,
                "emotion": None,
            })
    return labels


# ========== 第 4 步：小工具函数 ==========
def to_int(v):
    """把 True/False/None 统一转成 1/0/None，方便算 Kappa"""
    if v is True: return 1
    if v is False: return 0
    if v is None: return None
    return int(v)


# ========== 第 5 步：主流程 ==========
async def main():
    await pool.open()
    try:
        # 5.1 从数据库取这些 id 对应的标题（标题以数据库为准）
        ids = list(HUMAN_LABELS.keys())
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT id, title FROM viral_articles WHERE id = ANY(%s) ORDER BY id",
                    (ids,)
                )
                rows = await cur.fetchall()

        if len(rows) != len(ids):
            print(f"⚠️ 数据库里只找到 {len(rows)} 条，期望 {len(ids)} 条")
            return

        ids_found = [r[0] for r in rows]
        titles = [r[1] for r in rows]

        print(f"共 {len(titles)} 条标题\n")

        # 5.2 调 LLM 打标
        print("调用 LLM 打标...")
        llm_labels = label_batch(titles)
        llm_map = {item["index"]: item for item in llm_labels}

        # 5.3 逐特征对比
        features = ["has_number", "has_pain", "has_trend", "emotion"]

        print()
        print("=" * 62)
        print("Kappa 对比结果")
        print("=" * 62)

        for feat in features:
            human_vals = []
            llm_vals = []
            mismatches = []

            for i, db_id in enumerate(ids_found):
                h = to_int(HUMAN_LABELS[db_id].get(feat))
                lv = to_int(llm_map.get(i, {}).get(feat))

                if h is None or lv is None:
                    mismatches.append((db_id, titles[i], h, lv))
                    continue

                human_vals.append(h)
                llm_vals.append(lv)
                if h != lv:
                    mismatches.append((db_id, titles[i], h, lv))

            try:
                kappa = cohen_kappa_score(human_vals, llm_vals)
                kappa_str = f"{kappa:.3f}"
            except Exception as e:
                kappa_str = f"计算失败（{e}）"

            total_valid = len(human_vals)
            agree = sum(1 for a, b in zip(human_vals, llm_vals) if a == b)
            print()
            print(f"【{feat}】")
            print(f"  Kappa  = {kappa_str}")
            print(f"  一致率 = {agree}/{total_valid}")
            if mismatches:
                print(f"  不一致 / 缺失：")
                for db_id, title, h, l in mismatches:
                    print(f"    id={db_id}  {title[:35]}  人:{h} / LLM:{l}")

    finally:
        await pool.close()


# ========== 第 6 步：脚本入口 ==========
if __name__ == "__main__":
    asyncio.run(main())