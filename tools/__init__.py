# tools/__init__.py

from .brainstorm_topics import brainstorm_topics
from .generate_title import generate_title
from .write_article import write_article
from .polish_content import polish_content
from .analyze_stats import analyze_stats

TOOLS = {
    "brainstorm_topics": brainstorm_topics,
    "generate_title": generate_title,
    "write_article": write_article,
    "polish_content": polish_content,
    "analyze_stats": analyze_stats,
}