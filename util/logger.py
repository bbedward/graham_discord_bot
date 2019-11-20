import logging
from logging.handlers import TimedRotatingFileHandler, WatchedFileHandler

def get_logger(log_file : str, log_level : int = logging.INFO) -> Logger:
    root = logging.getLogger('graham')
    logging.basicConfig(level=log_level)
    handler = WatchedFileHandler(log_file)
    formatter = logging.Formatter("%(asctime)s;%(levelname)s;%(message)s", "%Y-%m-%d %H:%M:%S %z")
    handler.setFormatter(formatter)
    root.addHandler(handler)
    root.addHandler(TimedRotatingFileHandler(log_file, when="d", interval=1, backupCount=100))