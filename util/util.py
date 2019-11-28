from pathlib import Path

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