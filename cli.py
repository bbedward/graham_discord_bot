#!./venv/bin/python
import argparse
import sys
import os
from tortoise import Tortoise, run_async
from tortoise.utils import get_schema_sql
from db.models.secret import Secret
from util.random_util import RandomUtil

parser = argparse.ArgumentParser(description="Utilities for Graham TipBot")
parser.add_argument('-i', '--init', action='store_true',  help='Initialize the bot')
options = parser.parse_args()

async def create_db():
    await Tortoise.init(
        db_url='sqlite://dev.db',
        modules={'db': ['db.models.user', 'db.models.account', 'db.models.stats', 'db.models.secret']}
    )

async def init_db():
    # Create database
    print("Creating sqlite database")
    await create_db()
    # Generate the schema
    print("Generating schema")
    await Tortoise.generate_schemas()
    print("Database initialized")

async def init_seed_storage():
    await create_db() # connect
    has_seed = await Secret.all().count() > 0
    if not has_seed:
        while True:
            ans = input("Do you want to import an existing seed? (y/n):")
            ans_clean = ans.strip().lower()
            if ans_clean not in ['y', 'n']:
                print("Please enter 'y' or 'n'")
                continue
            elif ans_clean == 'n':
                print("Generating seed...")
                Secret()
                break
            elif ans_clean == 'y':
                print("enter seed")

if __name__ == '__main__':
    if options.init:
        try:
            run_async(init_db())
            run_async(init_seed_storage())
            print("Graham is initialized")
        except KeyboardInterrupt:
            print("\nExiting...")
    else:
        parser.print_help()
    sys.exit(0)