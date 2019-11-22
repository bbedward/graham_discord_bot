class CommandInfo(object):
    """Class to store information about a command (triggers, help info, etc.)"""

    def __init__(self, triggers: list = [], overview: str = '', details: str = '', example: str = ''):
        self.triggers = triggers
        self.overview = overview
        self.details = details
        self.example = example