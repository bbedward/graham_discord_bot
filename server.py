from aiohttp import web
from discord.ext.commands import Bot
from db.models.account import Account
from db.redis import RedisDB
from util.discord.messages import Messages
from util.env import Env

import config
import logging
import json

class GrahamServer(object):
    """An AIOHTTP server that listens for callbacks and provides various APIs"""
    def __init__(self, bot: Bot, host: str, port: int):
        self.bot = bot
        self.app = web.Application()
        self.app.add_routes([web.post('/callback', self.callback)])
        self.logger = logging.getLogger()
        self.host = host
        self.port = port
        self.min_amount = 10 if Env.banano() else 0.1

    async def callback(self, request: web.Request):
        """Route for handling HTTP callback"""
        request_json = await request.json()
        hash = request_json['hash']
        self.logger.debug(f"callback received {hash}")
        # cache
        if not await RedisDB.instance().exists(f"callback:{hash}"):
            await RedisDB.instance().set(f"callback:{hash}", "val", expires=300)
        else:
            return web.HTTPOk()
        # De-serialize block
        request_json['block'] = json.loads(request_json['block'])
        # only consider sends
        if 'is_send' in request_json and (request_json['is_send'] or request_json['is_send'] == 'true'):
            if 'amount' in request_json:
                # only consider self.min_amount or larger
                converted_amount = Env.raw_to_amount(int(request_json['amount']))
                if converted_amount >= self.min_amount:
                    # Figure out of this is one of our users
                    link = request_json['block']['link_as_account']
                    account = await Account.filter(address=link).prefetch_related('user').first()
                    if account is None:
                        return web.HTTPOk()
                    # See if this is an internal TX
                    internal = await RedisDB.instance().exists(f"hash:{hash}")
                    if internal:
                        return web.HTTPOk()
                    self.logger.debug(f'Deposit received: {request_json["amount"]} for {account.user.id}')
                    amount_string = f"{Env.raw_to_amount(int(request_json['amount']))} {Env.currency_symbol()}"
                    discord_user = await self.bot.fetch_user(account.user.id)
                    if discord_user is not None:
                        await Messages.send_success_dm(discord_user, f"Your deposit of **{amount_string}** has been received. It will be in your available balance shortly!", header="Deposit Success", footer=f"I only notify you of deposits that are {self.min_amount} {Env.currency_symbol()} or greater.")
        return web.HTTPOk()

    async def start(self):
        """Start the server"""
        runner = web.AppRunner(self.app, access_log = None if not config.Config.instance().debug else self.logger)
        await runner.setup()
        site = web.TCPSite(runner, self.host, self.port)
        await site.start()