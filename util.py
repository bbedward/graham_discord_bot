import logging
import logging.handlers

class BananoConversions():
    # 1 BANANO = 10e29 RAW
    RAW_PER_BAN = 10 ** 29

    @classmethod
    def raw_to_banano(self, raw_amt):
        return raw_amt / self.RAW_PER_BAN

    @staticmethod
    def banano_to_raw(ban_amt):
        expanded = float(ban_amt) * 100
        return int(expanded) * (10 ** 27)


class NanoConversions():
    # 1 rai = 10e24 RAW
    RAW_PER_RAI = 10 ** 24

    @classmethod
    def raw_to_rai(self, raw_amt):
        return raw_amt / self.RAW_PER_RAI

    @classmethod
    def rai_to_raw(self, rai_amt):
        return int(rai_amt) * self.RAW_PER_RAI

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
