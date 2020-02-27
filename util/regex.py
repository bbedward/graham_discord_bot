import re

from util.env import Env
from typing import List

class RegexUtil():
    @staticmethod
    def find_float(input: str) -> float:
        """Find a floating-point number in a string. Raises Exception if not found"""
        str_split = input.split('<@')
        if (len(str_split) == 0):
            raise AmountMissingException("amount_not_found")
        input_text = str_split[0]
        regex = r'(?:^|\s)(\d*\.?\d+)(?=$|\s)'
        matches = re.findall(regex, input_text, re.IGNORECASE)
        if len(matches) >= 1:
            return abs(float(matches[0].strip()))
        raise AmountMissingException("amount_not_found")

    @staticmethod
    def find_send_amounts(input_text: str) -> float:
        """find amount in outbound sends"""
        regex = r'(?:^|\s)(\d*\.?\d+)(?=$|\s)'
        matches = re.findall(regex, input_text, re.IGNORECASE)
        if len(matches) > 1:
            raise AmountAmbiguousException("amount_ambiguous")
        elif len(matches) == 1:
            return float(matches[0].strip())
        raise AmountMissingException("amount_not_found")

    @staticmethod
    def find_address_match(input_text: str) -> str:
        """Find nano/banano address in a string"""
        if Env.banano():
            address_regex = '(?:ban)(?:_)(?:1|3)(?:[13456789abcdefghijkmnopqrstuwxyz]{59})'
        else:
            address_regex = '(?:nano|xrb)(?:_)(?:1|3)(?:[13456789abcdefghijkmnopqrstuwxyz]{59})'
        matches = re.findall(address_regex, input_text)
        if len(matches) == 1:
            return matches[0]
        elif len(matches) > 1:
            raise AddressAmbiguousException("too_many_addresses")
        raise AddressMissingException("address_not_found")

    @staticmethod
    def find_address_matches(input_text: str) -> List[str]:
        """Find nano/banano addresses in a string"""
        if Env.banano():
            address_regex = '(?:ban)(?:_)(?:1|3)(?:[13456789abcdefghijkmnopqrstuwxyz]{59})'
        else:
            address_regex = '(?:nano|xrb)(?:_)(?:1|3)(?:[13456789abcdefghijkmnopqrstuwxyz]{59})'
        matches = re.findall(address_regex, input_text)
        if len(matches) >= 1:
            return matches
        raise AddressMissingException("address_not_found")

class AmountMissingException(Exception):
    pass

class AmountAmbiguousException(Exception):
    pass

class AddressMissingException(Exception):
    pass

class AddressAmbiguousException(Exception):
    pass
