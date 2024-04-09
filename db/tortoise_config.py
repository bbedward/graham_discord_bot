import logging
import os
from tortoise import Tortoise
from tortoise.contrib.aiohttp import register_tortoise

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

    def get_db_url(self) -> str:
        if self.use_postgres:
            self.logger.info("Using PostgreSQL Database {self.postgres_db}")
            return f'postgres://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}'
        self.logger.info(f"Using SQLite database dev.db")
        return f'sqlite://dev.db'

    def init_db_aiohttp(self, app):
        register_tortoise(app, db_url=self.get_db_url(),
                          modules=self.modules,
                          generate_schemas=True)

    async def init_db(self):
        await Tortoise.init(
            db_url=self.get_db_url(),
            modules=self.modules
        )
        # Create tables
        await Tortoise.generate_schemas(safe=True)
