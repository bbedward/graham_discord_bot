from tortoise import Tortoise

modules = {'db': ['db.models.user', 'db.models.account', 'db.models.stats', 'db.models.transaction', 'db.models.muted', 'db.models.favorite', 'db.models.giveaway']}

async def init_db():
    await Tortoise.init(
        db_url='sqlite://dev.db',
        modules=modules
    )
    await Tortoise.generate_schemas()