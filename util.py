import logging
import logging.handlers
import redis

RAW_PER_BAN=100000000000000000000000000000
RAW_PER_RAI=1000000000000000000000000

class TipBotException(Exception):
	def __init__(self, error_type):
		self.error_type = error_type
		Exception.__init__(self)

	def __str__(self):
		return repr(self.error_type)


def get_logger(name, log_file='debug.log'):
	formatter = logging.Formatter('%(asctime)s [%(name)s] -%(levelname)s- %(message)s')
	logger = logging.getLogger(name)
	logger.setLevel(logging.DEBUG)
	file_handler = logging.handlers.TimedRotatingFileHandler(log_file, when='midnight', backupCount=0)
	file_handler.setLevel(logging.DEBUG)
	file_handler.setFormatter(formatter)
	logger.handlers = []
	logger.addHandler(file_handler)
	console_handler = logging.StreamHandler()
	console_handler.setFormatter(formatter)
	logger.addHandler(console_handler)
	logger.propagate = False
	return logger

REDIS_CLIENT = redis.Redis()

def only_one(function=None, key="", timeout=None):
    """Enforce only one celery task at a time."""

    def _dec(run_func):
        """Decorator."""

        def _caller(*args, **kwargs):
            """Caller."""
            ret_value = None
            have_lock = False
            lock = REDIS_CLIENT.lock(key, timeout=timeout)
            try:
                have_lock = lock.acquire(blocking=False)
                if have_lock:
                    ret_value = run_func(*args, **kwargs)
            finally:
                if have_lock:
                    lock.release()

            return ret_value

        return _caller

    return _dec(function) if function is not None else _dec