import logging
import os
from tortoise import Tortoise, connections
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
            self.logger.info(f"Using PostgreSQL Database {self.postgres_db}")
            return f'postgres://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}'
        self.logger.info(f"Using SQLite database dev.db")
        return f'sqlite://dev.db'

    def get_config(self) -> dict:
        # Existing columns are naive timestamps, so keep tortoise's pre-1.0 use_tz behavior
        return {
            'connections': {'default': self.get_db_url()},
            'apps': {'db': {'models': self.modules['db'], 'default_connection': 'default'}},
            'use_tz': False
        }

    def init_db_aiohttp(self, app):
        register_tortoise(app, config=self.get_config(), generate_schemas=True)

    async def init_db(self):
        await Tortoise.init(config=self.get_config())
        # Create tables
        await Tortoise.generate_schemas(safe=True)
        await self.run_migrations()

    async def run_migrations(self):
        # generate_schemas(safe=True) never ALTERs existing tables, so schema changes to them
        # ship as SQL files in db/migrations and are applied here, once, in filename order
        if not self.use_postgres:
            return
        migrations_dir = os.path.join(os.path.dirname(__file__), 'migrations')
        if not os.path.isdir(migrations_dir):
            return
        conn = connections.get('default')
        await conn.execute_script('CREATE TABLE IF NOT EXISTS applied_migrations (name VARCHAR(255) PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())')
        rows = await conn.execute_query_dict('SELECT name FROM applied_migrations')
        applied = {row['name'] for row in rows}
        for name in sorted(os.listdir(migrations_dir)):
            if not name.endswith('.sql') or name in applied:
                continue
            with open(os.path.join(migrations_dir, name)) as f:
                await conn.execute_script(f.read())
            await conn.execute_query('INSERT INTO applied_migrations (name) VALUES ($1)', [name])
            self.logger.info(f"Applied migration {name}")
