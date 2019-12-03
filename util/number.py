class NumberUtil(object):
    @staticmethod
    def truncate_digits(in_number: float, max_digits: int) -> float:
        """Restrict maximum decimal digits by removing them"""
        working_num = int(in_number * (10 ** max_digits))
        return working_num / (10 ** max_digits)

    @staticmethod
    def format_float(in_number: float) -> str:
        """Format a float with un-necessary chars removed. E.g: 1.0000 == 1"""
        as_str = f"{in_number:.6f}".rstrip('0')
        if as_str[len(as_str) - 1] == '.':
            as_str = as_str.replace('.', '')
        return as_str
