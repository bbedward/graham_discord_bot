from util.env import Env

class Constants(object):
    TIP_MINIMUM = 1.0 if Env.banano() else 0.0001
    TIPRANDOM_MINIMUM = 5.0 if Env.banano() else 0.01
    TIP_UNIT = 'BAN' if Env.banano() else 'Nano'
    WITHDRAW_COOLDOWN = 1 # Seconds
    RAIN_MIN_ACTIVE_COUNT = 5 # Amount of people who have to be active for rain to work
    RAIN_MSG_REQUIREMENT = 5 # Amount of decent messages required to receive rain
    REPRESENTATIVE='ban_1tipbotgges3ss8pso6xf76gsyqnb69uwcxcyhouym67z7ofefy1jz7kepoy' if Env.banano() else 'nano_3o7uzba8b9e1wqu5ziwpruteyrs3scyqr761x7ke6w1xctohxfh5du75qgaj'
