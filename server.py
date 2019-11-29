from aiohttp import web
from discord.ext.commands import Bot
from db.models.account import Account

import logging
import json

class GrahamServer(object):
    """An AIOHTTP server that listens for callbacks and provides various APIs"""
    def __init__(self, bot: Bot, host: str, port: int):
        self.bot = bot
        self.app = web.Application()
        self.add_routes([web.post('/callback', self.callback)])
        self.logger = logging.getLogger()
        self.host = host
        self.port = port

    async def callback(self, request: web.Request):
        """Route for handling HTTP callback"""
        request_json = await request.json()
        hash = request_json['hash']
        self.logger.debug(f"callback received {hash}")
        # De-serialize block
        request_json['block'] = json.loads(request_json['block'])
        # Figure out of this is one of our users
        link = request_json['block']['link_as_account']
        user = await Account.filter(address=link).first()
        if user is None:
            return
        # Send user a DM letting em know we got their deposit
        # TODO - only do this for deposits, not tips

    async def start(self):
        """Start the server"""
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, self.host, self.port)
        await site.start()