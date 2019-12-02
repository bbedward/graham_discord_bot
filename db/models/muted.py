from tortoise.models import Model
from tortoise.transactions import in_transaction
from tortoise import fields

import db.models.user as usr

class Muted(Model):
    user = fields.ForeignKeyField('db.User', related_name='muted', index=True)
    target_user = fields.ForeignKeyField('db.User', related_name='muted_by')

    class Meta:
        table = 'muted'

    @staticmethod
    async def mute_user(muted_by: usr.User, muted_target: usr.User):
        m = await Muted.filter(user = muted_by, target_user = muted_target).first()
        if m is None:
            m = Muted(
                user = muted_by,
                target_user = muted_target
            )
            async with in_transaction() as conn:
                await m.save(using_db=conn)
        else:
            raise Exception("User is already muted")

    @staticmethod
    async def unmute_user(unmuted_by: usr.User, muted_target: usr.User):
        # TODO - Tortoise-ORM doesnt provide any feedback for deletes
        await Muted.filter(user=unmuted_by, target_user=muted_target).delete()