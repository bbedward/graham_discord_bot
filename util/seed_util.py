import string
import secrets

class SeedUtil():

    @staticmethod
    def generate_seed() -> str:
        return ''.join(secrets.choice(string.hexdigits) for _ in range(64)).upper()

    @staticmethod
    def seed_is_valid(seed: str) -> bool:
        # Check length
        if len(seed) != 64:
            return False
        # Ensure hex
        try:
            int(seed, 16)
        except ValueError:
            return False
        return True