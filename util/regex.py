import re

class RegexUtil():
    @staticmethod
    def find_float(input: str) -> float:
        """Find a floating-point number in a string. Raises Exception if not found"""
        str_split = input.split('<@')
        if (len(str_split) == 0):
            raise Exception("amount_not_found")
        input_text = str_split[0]
        regex = r'(?:^|\s)(\d*\.?\d+)(?=$|\s)'
        matches = re.findall(regex, input_text, re.IGNORECASE)
        if len(matches) >= 1:
            return float(matches[0].strip())
        else:
            raise Exception("amount_not_found")