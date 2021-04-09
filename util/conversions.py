import decimal

decimal.getcontext().prec = 39
decimal.getcontext().traps[decimal.Inexact] = 1

class BananoConversions():
    # 1 BANANO = 10e29 RAW
    @staticmethod
    def raw_to_banano(raw_amt: int) -> decimal.Decimal:
        return decimal.Decimal(raw_amt) / (10 ** 29)

    @staticmethod
    def banano_to_raw(ban_amt: decimal.Decimal) -> int:
        return int(ban_amt * (10 ** 29))

class NanoConversions():
    # 1 NANO = 10e30 RAW
    @staticmethod
    def raw_to_nano(raw_amt: int) -> decimal.Decimal:
        return decimal.Decimal(raw_amt) / (10 ** 30)

    @staticmethod
    def nano_to_raw(mnano_amt: decimal.Decimal) -> int:
        return int(mnano_amt * (10 ** 30))
