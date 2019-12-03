#!./venv/bin/python
from dotenv import load_dotenv
load_dotenv()

import argparse
import asyncio
import os
from models.constants import Constants
from db.tortoise_config import DBConfig
from db.models.account import Account
from rpc.client import RPCClient

parser = argparse.ArgumentParser(description="Utilities for Graham")
parser.add_argument('-r', '--representative-fix', action='store_true',  help='Set representative for all bot accounts')
options, unknown = parser.parse_known_args()

async def rep_fix():
    print("Starting rep set routine")
    await DBConfig().init_db()
    accounts = await Account.all()
    for a in accounts:
        # Get account info
        acct_info = await RPCClient.instance().account_info(a.address)
        if acct_info is not None and 'representative' in acct_info and acct_info['representative'] != Constants.REPRESENTATIVE:
            print(f"Setting rep for {a.address}")
            hash = await RPCClient.instance().account_representative_set(a.address, Constants.REPRESENTATIVE)
            if hash is not None:
                print(f"Set rep {hash}")
            else:
                print("Failed to set rep")
    print("Done")

if __name__ == '__main__':
    if options.representative_fix:
        print("Running rep fix")
        loop = asyncio.new_event_loop()
        loop.run_until_complete(rep_fix())
        loop.close()
    else:
        parser.print_help()
    exit(0)