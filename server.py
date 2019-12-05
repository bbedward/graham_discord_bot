from aiohttp import web
from discord.ext.commands import Bot
from db.models.account import Account
from db.models.user import User
from db.redis import RedisDB
from util.discord.messages import Messages
from util.env import Env
from util.regex import RegexUtil, AddressMissingException, AddressAmbiguousException

import config
import datetime
import logging
import rapidjson as json

class GrahamServer(object):
    """An AIOHTTP server that listens for callbacks and provides various APIs"""
    def __init__(self, bot: Bot, host: str, port: int):
        self.bot = bot
        self.app = web.Application()
        self.app.add_routes([
            web.post('/callback', self.callback),
            web.get('/ufw/{wallet}', self.ufw),
            web.get('/wfu/{user}', self.wfu),
            web.get('/users', self.users)
        ])
        self.logger = logging.getLogger()
        self.host = host
        self.port = port
        self.min_amount = 10 if Env.banano() else 0.1

    def format_js_iso(self, date: datetime.datetime) -> str:
        """Format a datetime object into a user-friendly representation"""
        return datetime.datetime.strftime(date, '%Y-%m-%dT%H:%M:%S.{0}Z').format(int(round(date.microsecond / 1000.0)))

    async def ufw(self, request: web.Request):
        """Return user info for specified wallet addresses
          e.g. http://server/wfu/ban_16n5c7qozokx661rneikh6e3mf978mc46qqjen7a51pwzood155bwrha6sfj+ban_37z6omyukgpgttq7bdagweaxdrdm5wjy7tdm97ggtkobdetme3bmhfayjowj"""
        if 'wallet' not in request.match_info:
            return web.HTTPBadRequest(reason="wallet is required")
        try:
            addresses = RegexUtil.find_address_matches(request.match_info['wallet'])
        except AddressMissingException:
            return web.HTTPBadRequest(reason="bad address specified")
        accounts = await Account.filter(address__in=addresses).prefetch_related('user').all()
        if accounts is None:
            return web.json_response(
                data={'error': 'user(s) not found'},
                dumps=json.dumps
            )
        resp = []
        for account in accounts:
            resp.append(
                {
                    'user_id': account.user.id,
                    'user_last_known_name': account.user.name,
                    'address': account.address,
                    'created_ts_utc': self.format_js_iso(account.user.created_at)
                }
            )
        return web.json_response(
            data=resp,
            dumps=json.dumps
        )

    async def wfu(self, request: web.Request):
        """Return user info for specified discord IDs
          e.g. http://server/wfu/303599885800964097+412286270694359052"""
        if 'user' not in request.match_info:
            return web.HTTPBadRequest(reason="user(s) is required")
        user_ids = []
        for u in request.match_info['user'].split('+'):
            try:
                user_ids.append(int(u.strip()))
            except ValueError:
                return web.HTTPBadRequest(reason="user IDs should be integers")
  
        users = await User.filter(id__in=user_ids).prefetch_related('account').all()
        if users is None:
            return web.json_response(
                data={'error': 'user(s) not found'},
                dumps=json.dumps
            )
        resp = []
        for user in users:
            resp.append(
                {
                    'user_id': user.id,
                    'user_last_known_name': user.name,
                    'address': user.account.address,
                    'created_ts_utc': self.format_js_iso(user.created_at)
                }
            )
        return web.json_response(
            data=resp,
            dumps=json.dumps
        )

    async def users(self, request: web.Request):
        cached = await RedisDB.instance().get("apiuserscache")
        if cached is not None:
            return web.json_response(
                data=json.loads(cached),
                dumps=json.dumps
            )
        # Get all of not cached
        users = await User.all().prefetch_related('account')
        resp = []
        for user in users:
            resp.append(
                {
                    'user_id': user.id,
                    'user_last_known_name': user.name,
                    'address': user.account.address,
                    'created_ts_utc': self.format_js_iso(user.created_at)
                }
            )
        await RedisDB.instance().set("apiuserscache", json.dumps(resp), expires=1800)
        return web.json_response(
            data=resp,
            dumps=json.dumps
        )

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