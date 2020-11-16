import logging
import os
from tortoise import Tortoise

class DBConfig(object):
    def __init__(self):
        self.logger = logging.getLogger()
        self.modules = {'db': ['db.models.user', 'db.models.account', 'db.models.stats', 'db.models.transaction', 'db.models.muted', 'db.models.favorite', 'db.models.giveaway']}
        self.use_postgres = False
        self.postgres_db = os.getenv('POSTGRES_DB')
        self.postgres_user = os.getenv('POSTGRES_USER')
        self.postgres_password = os.getenv('POSTGRES_PASSWORD')
        self.postgres_host = os.getenv('POSTGRES_HOST', '127.0.0.1')
        self.postgres_port = os.getenv('POSTGRES_PORT', 5432)
        if self.postgres_db is not None and self.postgres_user is not None and self.postgres_password is not None:
            self.use_postgres = True
        elif self.postgres_db is not None or self.postgres_user is not None or self.postgres_password is not None:
            raise Exception("ERROR: Postgres is not properly configured. POSTGRES_DB, POSTGRES_USER, and POSTGRES_PASSWORD environment variables are all required.")

    async def init_db(self):
        if self.use_postgres:
            self.logger.info(f"Using PostgreSQL Database {self.postgres_db}")
            await Tortoise.init(
                db_url=f'postgres://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}',
                modules=self.modules
            )
        else:
            self.logger.info(f"Using SQLite database dev.db")
            await Tortoise.init(
                db_url='sqlite://dev.db',
                modules=self.modules
            )
        # Create tables
        await Tortoise.generate_schemas(safe=True)
