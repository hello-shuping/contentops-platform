# tools/schemas.py

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "brainstorm_topics",
            "description": "批量专题策划。用户说'帮我策划几个专题'、'围绕XX有哪些方向'、'列一批选题'时调用",
            "strict": True,
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "领域或方向，比如'考研'、'考研英语'、'职场沟通'",
                    },
                    "goals": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": ["涨粉", "转化", "引流", "互动"],
                        },
                        "description": "目标类型，用户没说就传全部四个",
                    },
                    "count": {
                        "type": "integer",
                        "description": "每个目标下几个专题，默认 5",
                    },
                },
                "required": ["topic", "goals", "count"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_title",
            "description": "生成标题",
            "strict": True,
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "主题。如果用户提到了平台（小红书/知乎/公众号），把它一起写进 topic，比如'小红书考研文案'",
                    },
                    "count": {
                        "type": "integer",
                        "description": "生成数量，如果用户没有明确指定，默认填 5",
                    },
                    "style": {
                        "type": "string",
                        "enum": ["干货型", "轻松型", "故事感", "种草型"],
                        "description": "标题风格，默认干货型",
                    },
                },
                "required": ["topic", "count", "style"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_article",
            "description": "写文章",
            "strict": True,
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "主题。如果用户提到了平台（小红书/知乎/公众号），把它一起写进 topic，比如'小红书考研文案'",
                    },
                    "word_count": {
                        "type": "integer",
                        "description": "字数，默认1200",
                    },
                    "style": {
                        "type": "string",
                        "enum": ["正式", "轻松", "专业", "故事感", "口语化"],
                        "description": "风格，默认正式",
                    },
                },
                "required": ["topic", "word_count", "style"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "polish_content",
            "description": "润色内容",
            "strict": True,
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "原文",
                    },
                    "style": {
                        "type": "string",
                        "enum": ["正式", "轻松", "专业", "故事感", "口语化"],
                        "description": "风格，默认正式",
                    },
                },
                "required": ["text", "style"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_stats",
            "description": "分析用户导入的文章运营数据，返回互动率、收藏率排名和规律。用户说'分析一下数据'、'看看哪篇效果好'时调用",
            "parameters": {
                "type": "object",
                "properties": {
                    "platform": {
                        "type": "string",
                        "description": "平台，小红书或公众号，默认小红书",
                    },
                },
            },
        },
    },
]