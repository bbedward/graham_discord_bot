from aiohttp import web
from db.models.account import Account
from db.models.user import User
from db.redis import RedisDB
from models.constants import Constants
from util.env import Env
from util.regex import RegexUtil, AddressMissingException, AddressAmbiguousException

import aiohttp_cors
import config
import datetime
import logging
import rapidjson as json
import string
import random
from typing import List
from db.models.transaction import Transaction

class GrahamServer(object):
    """An AIOHTTP server that listens for callbacks and provides various APIs"""
    def __init__(self, subID: str, host: str, port: int):
        self.subID = subID
        self.app = web.Application(middlewares=[web.normalize_path_middleware()])
        self.app.add_routes([
            web.post('/callback', self.callback)
        ])
        cors = aiohttp_cors.setup(self.app, defaults={
            "*": aiohttp_cors.ResourceOptions(
                    allow_credentials=True,
                    expose_headers="*",
                    allow_headers="*",
                )
        })
        ufw_resource = cors.add(self.app.router.add_resource("/ufw/{wallet}"))
        cors.add(ufw_resource.add_route("GET", self.ufw)) 
        wfu_resource = cors.add(self.app.router.add_resource("/wfu/{user}"))
        cors.add(wfu_resource.add_route("GET", self.wfu))
        users_resource = cors.add(self.app.router.add_resource("/users"))
        cors.add(users_resource.add_route("GET", self.users))
        active_resource = cors.add(self.app.router.add_resource("/active/{server_id}"))
        cors.add(active_resource.add_route("GET", self.get_active))
        self.logger = logging.getLogger()
        self.host = host
        self.port = port
        self.min_amount = 10 if Env.banano() else 0.1

    def format_js_iso(self, date: datetime.datetime) -> str:
        """Format a datetime object into a user-friendly representation"""
        return datetime.datetime.strftime(date, '%Y-%m-%dT%H:%M:%S.{0}Z').format(int(round(date.microsecond / 1000.0)))

    async def get_active(self, request: web.Request) -> List[User]:
        """Return a list of active users"""
        redis = await RedisDB.instance().get_redis()

        if 'server_id' not in request.match_info:
            return web.HTTPBadRequest(reason='server_id is required')
        try:
            server_id = int(request.match_info['server_id'])
        except ValueError:
            return web.HTTPBadRequest(reason='server_id must be an integer')

        # Get all activity stats from DB
        users_list = []
        async for key in redis.iscan(match=f"*activity:{server_id}*"):
            u = await redis.get(key)
            if u is not None:
                users_list.append(json.loads(u))

        if len(users_list) == 0:
            return web.json_response(
                data=[],
                dumps=json.dumps
            )

        # Get IDs that meet requirements
        users_filtered = []
        for u in users_list:
            if u['msg_count'] >= Constants.RAIN_MSG_REQUIREMENT:
                users_filtered.append(u['user_id'])

        if len(users_filtered) < 1:
            return web.json_response(
                data=[],
                dumps=json.dumps
            )

        # Get only users in our database
        ret = await User.filter(id__in=users_filtered, frozen=False, tip_banned=False).prefetch_related('account').all()
        ret_json = []
        for u in ret:
            ret_json.append({
                "id":u.id,
                "address":await u.get_address()
            })
        return web.json_response(
            data=ret_json,
            dumps=json.dumps
        )

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
                    transaction = await Transaction.filter(block_hash=hash).prefetch_related('receiving_user').first()
                    if transaction is not None and transaction.receiving_user is not None:
                        return web.HTTPOk()
                    self.logger.debug(f'Deposit received: {request_json["amount"]} for {account.user.id}')
                    amount_string = f"{Env.raw_to_amount(int(request_json['amount']))} {Env.currency_symbol()}"
                    redis = await RedisDB.instance().get_redis()
                    self.logger.info(self.subID)
                    await redis.publish_json(self.subID, {
                        "id": account.user.id,
                        "message": f"Your deposit of **{amount_string}** has been received. It will be in your available balance shortly!",
                    })
        return web.HTTPOk()

    def start(self):
        """Start the server"""
        web.run_app(self.app, host=self.host, port=self.port,  access_log = None if not config.Config.instance().debug else self.logger)