import re

from util.env import Env
from typing import List

class RegexUtil():
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

class AddressMissingException(Exception):
    pass

class AddressAmbiguousException(Exception):
    pass
