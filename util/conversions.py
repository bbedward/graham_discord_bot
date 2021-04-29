import decimal

NANO_DECIMALS = decimal.Decimal(10) ** -6
BANANO_DECIMALS = decimal.Decimal(10) ** -2

class BananoConversions():
    # 1 BANANO = 10e29 RAW
    @staticmethod
    def raw_to_banano(raw_amt: int) -> float:
        decimal_amt = decimal.Decimal(raw_amt) / (10 ** 29)
        decimal_amt = decimal_amt.quantize(BANANO_DECIMALS, decimal.ROUND_DOWN)
        return float(decimal_amt)

    @staticmethod
    def banano_to_raw(ban_amt: float) -> int:
        decimal_amt = decimal.Decimal(str(ban_amt))
        decimal_amt = decimal_amt.quantize(BANANO_DECIMALS, decimal.ROUND_DOWN)
        return int(decimal_amt * (10 ** 29))

class NanoConversions():
    # 1 NANO = 10e30 RAW
    @staticmethod
    def raw_to_nano(raw_amt: int) -> float:
        decimal_amt = decimal.Decimal(raw_amt) / (10 ** 30)
        decimal_amt = decimal_amt.quantize(NANO_DECIMALS, decimal.ROUND_DOWN)
        return float(decimal_amt)

    @staticmethod
    def nano_to_raw(mnano_amt: float) -> int:
        decimal_amt = decimal.Decimal(str(mnano_amt))
        decimal_amt = decimal_amt.quantize(NANO_DECIMALS, decimal.ROUND_DOWN)
        return int(decimal_amt * (10 ** 30))
