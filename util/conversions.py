import decimal

class BananoConversions():
    # 1 BANANO = 10e29 RAW
    @staticmethod
    def raw_to_banano(raw_amt: int) -> float:
        return raw_amt / (10 ** 29)

    @staticmethod
    def banano_to_raw(ban_amt: float) -> int:
        asStr = str(ban_amt).split(".")
        banAmount = int(asStr[0])
        if len(asStr[1]) > 2:
            asStr[1] = asStr[1][:2]
        asStr[1] = asStr[1].ljust(2, '0')
        banoshiAmount = int(asStr[1])
        return (banAmount * (10**29)) + (banoshiAmount * (10 ** 27))


class NanoConversions():
    # 1 NANO = 10e30 RAW
    @staticmethod
    def raw_to_nano(raw_amt: int) -> float:
        return raw_amt / (10 ** 30)

    @staticmethod
    def nano_to_raw(mnano_amt: float) -> int:
        asStr = str(mnano_amt).split(".")
        nanoAmount = int(asStr[0])
        if len(asStr[1]) > 6:
            asStr[1] = asStr[1][:6]
        asStr[1] = asStr[1].ljust(6, '0')
        nanoshiAmount = int(asStr[1])
        return (nanoAmount * (10**30)) + (nanoshiAmount * (10 ** 24))