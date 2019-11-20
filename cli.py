#!./venv/bin/python
import argparse
import sys

parser = argparse.ArgumentParser(description="Utilities for Graham TipBot")
parser.add_argument('-i', '--init', action='store_true',  help='Initialize the bot')
options = parser.parse_args()

if __name__ == '__main__':
    if options.init:
        try:
            print("Graham is initialized")
        except KeyboardInterrupt:
            print("\nExiting...")
    else:
        parser.print_help()
    sys.exit(0)