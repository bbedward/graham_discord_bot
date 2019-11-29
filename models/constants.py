from util.env import Env

class Constants(object):
    TIP_MINIMUM = 1.0 if Env.banano() else 0.0001
    TIP_UNIT = 'BAN' if Env.banano() else 'Nano'
    WITHDRAW_COOLDOWN = 1 # Seconds
    # TODO - set to 1 for testing
    RAIN_MIN_ACTIVE_COUNT = 1 # Amount of people who have to be active for rain to work
    RAIN_MSG_REQUIREMENT = 1 # Amount of decent messages required to receive rain