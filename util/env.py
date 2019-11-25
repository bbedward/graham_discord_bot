import os

from util.conversions import BananoConversions, NanoConversions

class Env():
    @staticmethod
    def banano() -> bool:
        return True if os.getenv('BANANO', None) is not None else False

    @staticmethod
    def raw_to_amount(raw_amt : int) -> float:
        return BananoConversions.raw_to_banano(raw_amt) if Env.banano() else NanoConversions.raw_to_nano(raw_amt)

    @staticmethod
    def amount_to_raw(amount : float) -> int:
        return BananoConversions.banano_to_raw(amount) if Env.banano() else NanoConversions.nano_to_raw(amount)

    @staticmethod
    def currency_name() -> str:
        return 'BANANO' if Env.banano() else 'Nano'

    @staticmethod
    def currency_symbol() -> str:
        return 'BAN' if Env.banano() else 'NANO'