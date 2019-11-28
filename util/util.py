from pathlib import Path

class Utils(object):
    """Generic utilities"""
    @staticmethod
    def get_project_root():
        return Path(__file__).parent.parent