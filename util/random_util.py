import string
import secrets

class RandomUtil():

    @staticmethod
    def generate_seed() -> str:
        return ''.join(secrets.choice(string.hexdigits) for _ in range(64)).upper()