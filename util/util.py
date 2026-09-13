from pathlib import Path
from typing import List

import asyncio
import secrets

class Utils(object):
    """Generic utilities"""
    @staticmethod
    def get_project_root():
        return Path(__file__).parent.parent

    @staticmethod
    async def run_task_list(task_list: List[asyncio.Future]):
        """Run a list of tasks, this is mainly to throttle some background tasks from running too quickly"""
        for t in task_list:
            await t

    @staticmethod
    def random_float() -> float:
        return secrets.randbelow(100) / 100