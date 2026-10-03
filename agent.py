# agent.py

import json
from openai import AsyncOpenAI

from config import config
from db.ccs import save_to_db, load_history, clear_history
from content.own import init_db_own
from content.viral import init_db_viral
from tools import TOOLS
from tools.schemas import TOOL_SCHEMAS
from logger import logger


client = AsyncOpenAI(
    api_key=config.API_KEY,
    base_url=config.BASE_URL
)

# init_db() 那些建表调用不用再放在这里了
# 已经挪到 main.py 的 lifespan 里，服务启动时统一执行



async def chat_stream(user_id, user_input):
    # ===== 命令：查看历史 =====
    if user_input.strip().lower() == "/history":
        messages = await load_history(user_id, 10, config.SYSTEM_PROMPT)
        lines = []
        for m in messages:
            if m["role"] == "user":
                lines.append(f"你：{m['content']}")
            elif m["role"] == "assistant":
                lines.append(f"AI：{m['content']}")
        yield "\n".join(lines) if lines else "暂无历史记录"
        return

    # ===== 命令：清空历史 =====
    if user_input.strip().lower() == "/delete":
        await clear_history(user_id)
        yield "已清空历史记录"
        return
    # ===========================

    # 1. 加载历史（无状态，直接查库） + 追加当前输入
    messages = await load_history(user_id, 5, config.SYSTEM_PROMPT)
    messages.append({"role": "user", "content": user_input})

    ai_reply = ""
    try:
        # 2. 第一次调用大模型 —— 流式
        response = await client.chat.completions.create(
            model=config.MODEL,
            messages=messages,
            tools=TOOL_SCHEMAS,
            tool_choice="auto",
            stream=True,
        )

        content = ""
        tool_calls_buffer = {}

        async for chunk in response:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta

            if delta.content:
                content += delta.content
                yield delta.content

            if delta.tool_calls:
                for tc in delta.tool_calls:
                    idx = tc.index
                    if idx not in tool_calls_buffer:
                        tool_calls_buffer[idx] = {"name": "", "arguments": ""}
                    if tc.function and tc.function.name:
                        tool_calls_buffer[idx]["name"] += tc.function.name
                    if tc.function and tc.function.arguments:
                        tool_calls_buffer[idx]["arguments"] += tc.function.arguments

        # 3. 判断是否有工具调用
        if tool_calls_buffer:
            tc = tool_calls_buffer[0]
            tool_name = tc["name"]
            tool_args = json.loads(tc["arguments"])
            logger.info(f"检测到工具调用: {tool_name}, 参数: {tool_args}")

            # 执行工具
            tool_prompt = await TOOLS[tool_name](**tool_args)
            logger.info(f"工具返回内容: {repr(tool_prompt)[:300]}")

            # ============= 核心修复区：补全上下文 =============
            # 3.1 把大模型刚才的“工具调用指令”追加进去
            messages.append({
                "role": "assistant",
                "tool_calls": [{
                    "id": "call_abc",  # 实际开发应该用大模型返回的真实 id，这里简化
                    "type": "function",
                    "function": {"name": tool_name, "arguments": tc["arguments"]}
                }]
            })
            
            # 3.2 把工具执行的结果追加进去，角色是 "tool"
            messages.append({
                "role": "tool",
                "tool_call_id": "call_abc",
                "content": str(tool_prompt)
            })
            # ==================================================

            # 4. 第二次调用大模型 —— 传入完整上下文！
            response2 = await client.chat.completions.create(
                model=config.MODEL,
                messages=messages,  # 注意！这里改成了 messages
                stream=True,
            )

            async for chunk in response2:
                if chunk.choices[0].delta.content:
                    ai_reply += chunk.choices[0].delta.content
                    yield chunk.choices[0].delta.content

            logger.info(f"工具 {tool_name} 执行完成")
        else:
            # 5. 没有工具调用，直接使用第一次生成的内容
            logger.info("未检测到工具调用，直接返回")
            ai_reply = content

    except Exception as e:
        logger.error(f"流式异常: {e}")
        yield "抱歉，服务暂时不可用，请稍后再试。"
        
    finally:
        # 6. 无论是否异常、是否中途断网，只要生成了内容，就存入数据库
        if ai_reply:
            await save_to_db(user_id, user_input, ai_reply)