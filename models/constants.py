from util.env import Env

class Constants():
    TIP_MINIMUM = 1.0 if Env.banano() else 0.0001
    TIP_UNIT = 'BAN' if Env.banano() else 'Nano'