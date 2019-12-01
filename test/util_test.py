import asyncio
import unittest
import os
from util.conversions import BananoConversions, NanoConversions
from util.number import NumberUtil
from util.regex import RegexUtil, AmountAmbiguousException, AmountMissingException, AddressAmbiguousException, AddressMissingException

def async_test(coro):
    def wrapper(*args, **kwargs):
        loop = asyncio.new_event_loop()
        return loop.run_until_complete(coro(*args, **kwargs))
    return wrapper

class TestConversions(unittest.TestCase):
    def test_unit_conversions(self):
        self.assertEqual(BananoConversions.raw_to_banano(101000000000000000000000000000), 1.01)
        self.assertEqual(BananoConversions.banano_to_raw(1.01), 101000000000000000000000000000)
        self.assertEqual(NanoConversions.raw_to_nano(123456789000000000000000000000000), 123.456789)
        self.assertEqual(NanoConversions.nano_to_raw(123.456789), 123456789000000000000000000000000)

class TestNumberUtil(unittest.TestCase):
    def test_truncate_digits(self):
        self.assertEqual(NumberUtil.truncate_digits(1.239, max_digits=2), 1.23)
        self.assertEqual(NumberUtil.truncate_digits(1.2, max_digits=2), 1.2)
        self.assertEqual(NumberUtil.truncate_digits(0.9999999999999, max_digits=6), 0.999999)

    def test_format_float(self):
        self.assertEqual(NumberUtil.format_float(9.90000), "9.9")
        self.assertEqual(NumberUtil.format_float(9.0), "9")
        self.assertEqual(NumberUtil.format_float(9), "9")
        self.assertEqual(NumberUtil.format_float(9.9000010), "9.900001")

class TestRegexUtil(unittest.TestCase):
    def test_find_float(self):
        self.assertEqual(RegexUtil.find_float('Hello 1.23 World'), 1.23)
        self.assertEqual(RegexUtil.find_float('Hello 1.23  4.56 World'), 1.23)
        with self.assertRaises(AmountMissingException) as exc:
            RegexUtil.find_float('Hello World')

    def test_find_send_amounts(self):
        self.assertEqual(RegexUtil.find_send_amounts('Hello 1.23 World'), 1.23)
        with self.assertRaises(AmountMissingException):
            RegexUtil.find_send_amounts('Hello World')
        with self.assertRaises(AmountAmbiguousException):
            RegexUtil.find_send_amounts('Hello 1.23 4.56 World')

    def test_find_address(self):
        os.environ['BANANO'] = 'true'
        self.assertEqual(RegexUtil.find_address_match('sdasdasban_3jb1fp4diu79wggp7e171jdpxp95auji4moste6gmc55pptwerfjqu48oksesdadasd'), 'ban_3jb1fp4diu79wggp7e171jdpxp95auji4moste6gmc55pptwerfjqu48okse')
        with self.assertRaises(AddressAmbiguousException):
            RegexUtil.find_address_match('sdasdban_3jb1fp4diu79wggp7e171jdpxp95auji4moste6gmc55pptwerfjqu48oksesdasd ban_3jb1fp4diu79wggp7e171jdpxp95auji4moste6gmc55pptwerfjqu48okse sban_3jb1fp4diu79wggp7e171jdpxp95auji4moste6gmc55pptwerfjqu48okse')
        with self.assertRaises(AddressMissingException):
            RegexUtil.find_address_match('sdadsd')

        del os.environ['BANANO']
        self.assertEqual(RegexUtil.find_address_match('sdasdasnano_3jb1fp4diu79wggp7e171jdpxp95auji4moste6gmc55pptwerfjqu48oksesdadasd'), 'nano_3jb1fp4diu79wggp7e171jdpxp95auji4moste6gmc55pptwerfjqu48okse')
        with self.assertRaises(AddressAmbiguousException):
            RegexUtil.find_address_match('sdasdnano_3jb1fp4diu79wggp7e171jdpxp95auji4moste6gmc55pptwerfjqu48oksesdasd nano_3jb1fp4diu79wggp7e171jdpxp95auji4moste6gmc55pptwerfjqu48okse snano_3jb1fp4diu79wggp7e171jdpxp95auji4moste6gmc55pptwerfjqu48okse')
        with self.assertRaises(AddressMissingException):
            RegexUtil.find_address_match('sdadsd')
        # XRB
        self.assertEqual(RegexUtil.find_address_match('sdasdasxrb_3jb1fp4diu79wggp7e171jdpxp95auji4moste6gmc55pptwerfjqu48oksesdadasd'), 'xrb_3jb1fp4diu79wggp7e171jdpxp95auji4moste6gmc55pptwerfjqu48okse')
        with self.assertRaises(AddressAmbiguousException):
            RegexUtil.find_address_match('sdasdxrb_3jb1fp4diu79wggp7e171jdpxp95auji4moste6gmc55pptwerfjqu48oksesdasd xrb_3jb1fp4diu79wggp7e171jdpxp95auji4moste6gmc55pptwerfjqu48okse sxrb_3jb1fp4diu79wggp7e171jdpxp95auji4moste6gmc55pptwerfjqu48okse')
        with self.assertRaises(AddressMissingException):
            RegexUtil.find_address_match('sdadsd')

    def test_find_addresses(self):
        # Multiple addresses
        os.environ['BANANO'] = 'true'
        self.assertEqual(RegexUtil.find_address_matches('sdasdasban_3jb1fp4diu79wggp7e171jdpxp95auji4moste6gmc55pptwerfjqu48oksesdadasd'), ['ban_3jb1fp4diu79wggp7e171jdpxp95auji4moste6gmc55pptwerfjqu48okse'])
        self.assertEqual(RegexUtil.find_address_matches('sdasdban_3jb1fp4diu79wggp7e171jdpxp95auji4moste6gmc55pptwerfjqu48oksesdasd ban_3jb1fp4diu79wggp7e171jdpxp95auji4moste6gmc55pptwerfjqu48okse sban_3jb1fp4diu79wggp7e171jdpxp95auji4moste6gmc55pptwerfjqu48okse'), ['ban_3jb1fp4diu79wggp7e171jdpxp95auji4moste6gmc55pptwerfjqu48okse', 'ban_3jb1fp4diu79wggp7e171jdpxp95auji4moste6gmc55pptwerfjqu48okse', 'ban_3jb1fp4diu79wggp7e171jdpxp95auji4moste6gmc55pptwerfjqu48okse'])
        with self.assertRaises(AddressMissingException):
            RegexUtil.find_address_matches('sdadsd')

        del os.environ['BANANO']
        self.assertEqual(RegexUtil.find_address_matches('sdasdasnano_3jb1fp4diu79wggp7e171jdpxp95auji4moste6gmc55pptwerfjqu48oksesdadasd'), ['nano_3jb1fp4diu79wggp7e171jdpxp95auji4moste6gmc55pptwerfjqu48okse'])
        self.assertEqual(RegexUtil.find_address_matches('sdasdnano_3jb1fp4diu79wggp7e171jdpxp95auji4moste6gmc55pptwerfjqu48oksesdasd nano_3jb1fp4diu79wggp7e171jdpxp95auji4moste6gmc55pptwerfjqu48okse snano_3jb1fp4diu79wggp7e171jdpxp95auji4moste6gmc55pptwerfjqu48okse'), ['nano_3jb1fp4diu79wggp7e171jdpxp95auji4moste6gmc55pptwerfjqu48okse', 'nano_3jb1fp4diu79wggp7e171jdpxp95auji4moste6gmc55pptwerfjqu48okse', 'nano_3jb1fp4diu79wggp7e171jdpxp95auji4moste6gmc55pptwerfjqu48okse'])
        with self.assertRaises(AddressMissingException):
            RegexUtil.find_address_matches('sdadsd')
        # XRB
        self.assertEqual(RegexUtil.find_address_matches('sdasdasxrb_3jb1fp4diu79wggp7e171jdpxp95auji4moste6gmc55pptwerfjqu48oksesdadasd'), ['xrb_3jb1fp4diu79wggp7e171jdpxp95auji4moste6gmc55pptwerfjqu48okse'])
        self.assertEqual(RegexUtil.find_address_matches('sdasdxrb_3jb1fp4diu79wggp7e171jdpxp95auji4moste6gmc55pptwerfjqu48oksesdasd xrb_3jb1fp4diu79wggp7e171jdpxp95auji4moste6gmc55pptwerfjqu48okse sxrb_3jb1fp4diu79wggp7e171jdpxp95auji4moste6gmc55pptwerfjqu48okse'), ['xrb_3jb1fp4diu79wggp7e171jdpxp95auji4moste6gmc55pptwerfjqu48okse', 'xrb_3jb1fp4diu79wggp7e171jdpxp95auji4moste6gmc55pptwerfjqu48okse', 'xrb_3jb1fp4diu79wggp7e171jdpxp95auji4moste6gmc55pptwerfjqu48okse'])
        with self.assertRaises(AddressMissingException):
            RegexUtil.find_address_matches('sdadsd')