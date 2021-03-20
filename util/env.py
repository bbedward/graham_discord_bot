import os

from util.conversions import BananoConversions, NanoConversions

class Env():
    @staticmethod
    def banano() -> bool:
        return True if os.getenv('BANANO', None) is not None else False

    @staticmethod
    def raw_to_amount(raw_amt: int) -> float:
        converted = BananoConversions.raw_to_banano(raw_amt) if Env.banano() else NanoConversions.raw_to_nano(raw_amt)
        return converted

    @staticmethod
    def amount_to_raw(amount: float) -> int:
        return BananoConversions.banano_to_raw(amount) if Env.banano() else NanoConversions.nano_to_raw(amount)

    @staticmethod
    def currency_name() -> str:
        return 'BANANO' if Env.banano() else 'Nano'

    @staticmethod
    def currency_symbol() -> str:
        return 'BAN' if Env.banano() else 'NANO'

    @staticmethod
    def precision_digits() -> int:
        return 2 if Env.banano() else 6

    @staticmethod
    def donation_address() -> str:
        return 'ban_1bboss18y784j9rbwgt95uwqamjpsi9oips5syohsjk37rn5ud7ndbjq61ft' if Env.banano() else 'nano_1bboss18y784j9rbwgt95uwqamjpsi9oips5syohsjk37rn5ud7ndbjq61ft'

    @classmethod
    def truncate_digits(in_number: float, max_digits: int) -> float:
        """Restrict maximum decimal digits by removing them"""
        working_num = int(in_number * (10 ** max_digits))
        return working_num / (10 ** max_digits)

    @classmethod
    def format_float(cls, in_number: float) -> str:
        """Format a float with un-necessary chars removed. E.g: 1.0000 == 1"""
        if not cls.banano()
            in_number = cls.truncate_digits(in_number, 6)
            as_str = f"{in_number:.6f}".rstrip('0')
        else:
            in_number = cls.truncate_digits(in_number, 2)
            as_str = f"{in_number:.2f}".rstrip('0')  
        as_str = f"{in_number:.6f}".rstrip('0')
        if as_str[len(as_str) - 1] == '.':
            as_str = as_str.replace('.', '')
        return as_str