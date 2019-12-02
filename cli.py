#!./venv/bin/python
import argparse
import asyncio
from models.constants import Constants
from db.models.account import Account
from rpc.client import RPCClient

parser = argparse.ArgumentParser(description="Utilities for Graham")
parser.add_argument('-r', '--representative-fix', action='store_true',  help='Set representative for all bot accounts')
options = parser.parse_args()

async def rep_fix():
    accounts = await Account.all()
    for a in accounts:
        # Get account info
        acct_info = await RPCClient.instance().account_info(a.address)
        if 'representative' in acct_info and acct_info['representative'] != Constants.REPRESENTATIVE:
            print(f"Setting rep for {a.address}")
            hash = await RPCClient.instance().account_representative_set(a.address, Constants.REPRESENTATIVE)
            if hash is not None:
                print(f"Set rep {hash}")
            else:
                print("Failed to set rep")

if __name__ == '__main__':
    if options.representative_fix:
        print("Running rep fix")
        loop = asyncio.new_event_loop()
        loop.run_until_complete(rep_fix())
    else:
        parser.print_help()
    exit(0)