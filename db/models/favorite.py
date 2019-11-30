from tortoise.models import Model
from tortoise import fields

import db.models.user as usr

class Favorite(Model):
    user = fields.ForeignKeyField('db.User', related_name='favorites', index=True)
    favorited_user = fields.ForeignKeyField('db.User', related_name='favorited_by')

    class Meta:
        table = 'favorites'

    @staticmethod
    async def add_favorite(favorited_by: usr.User, favorited_target: usr.User):
        m = await Favorite.filter(user = favorited_by, favorited_user = favorited_by).first()
        if m is None:
            m = Favorite(
                user = favorited_by,
                favorited_user = favorited_target
            )
            await m.save()
        else:
            raise Exception("User is already favorited")

    @staticmethod
    async def delete_favorite(favorited_by: usr.User, favorited_target: usr.User):
        # TODO - Tortoise-ORM doesnt provide any feedback for deletes
        await Favorite.filter(user=favorited_by, favorited_user=favorited_target).delete()