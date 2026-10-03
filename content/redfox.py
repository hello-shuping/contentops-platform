# redfox.py
import os
from redfox import RedFoxClient
from config import config

client = RedFoxClient(api_key=config.REDFOX_API_KEY)


def search_xhs_notes(keyword: str, sort_type: str = "4", limit: int = 50):
    result = client.xiaohongshu.search_articles(
        keyword=keyword,
        sort_type=sort_type
    )
    return result.get("list", [])[:limit]