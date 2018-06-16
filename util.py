import logging
import logging.handlers

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
