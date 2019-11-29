from pathlib import Path
from typing import List

import asyncio
import emoji
import re

class Utils(object):
    """Generic utilities"""
    @staticmethod
    def get_project_root():
        return Path(__file__).parent.parent

    @staticmethod
    def emoji_strip(content: str) -> str:
        """Strips emojis out of a string, returns resulting string"""
        modified = re.sub(emoji.get_emoji_regexp(), r"", content)
        modified = re.sub(':[^>]+:', '', modified)
        modified = re.sub('<[^>]+>', '', modified)
        return modified.strip()

    @staticmethod
    async def run_task_list(task_list: List[asyncio.Future]):
        """Run a list of tasks, this is mainly to throttle some background tasks from running too quickly"""
        for t in task_list:
            await t