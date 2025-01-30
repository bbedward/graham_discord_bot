from pathlib import Path
from typing import List

import aiohttp
import asyncio
import emoji
import rapidjson as json
import re
import secrets

class BNSResolvingException(Exception):
    pass

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

    @staticmethod
    def random_float() -> float:
        return secrets.randbelow(100) / 100

    @staticmethod
    async def resolve_bns(domain_and_tld: str) -> dict:
        parts = domain_and_tld.split('.')
        async with aiohttp.ClientSession(json_serialize=json.dumps) as session:
            async with session.post("https://api.creeper.banano.cc/banano/v1/account/bns", json={
                'domain_name': parts[0],
                'tld': parts[1],
            }, timeout=300) as resp:
                respJson = await resp.json()
                if resp.status != 200:
                    self.logger.error(f"BNS resolve request failed with status {resp.status}")
                    self.logger.error(f"Request: {req_json}")
                    self.logger.error(f"Response: {respJson}")
                return respJson
