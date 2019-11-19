#!./venv/bin/python
import argparse
import sys
from tortoise import Tortoise, run_async
from tortoise.utils import get_schema_sql

parser = argparse.ArgumentParser(description="Utilities for Graham TipBot")
parser.add_argument('-i', '--init', action='store_true',  help='Initialize the bot')
options = parser.parse_args()

async def init_db():
    # Create database
    print("Creating sqlite database")
    await Tortoise.init(
        db_url='sqlite://dev.db',
        modules={'db': ['db.models.user', 'db.models.account', 'db.models.stats']}
    )
    # Generate the schema
    print("Generating schema")
    await Tortoise.generate_schemas()
    print("Database initialized")

if __name__ == '__main__':
    if options.init:
        run_async(init_db())
        print("Graham is initialized")
    else:
        parser.print_help()
    sys.exit(0)