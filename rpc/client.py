import aiohttp
import rapidjson as json
import socket
from config import Config
from typing import List, Tuple

class RPCClient(object):
    _instance = None

    def __init__(self):
        raise RuntimeError('Call instance() instead')

    @classmethod
    def instance(cls) -> 'RPCClient':
        if cls._instance is None:
            cls._instance = cls.__new__(cls)
            cls.node_url = Config.instance().node_url
            cls.node_port = Config.instance().node_port
            cls.wallet_id = Config.instance().wallet
            cls.ipv6 = '::' in cls.node_url
            cls.connector = aiohttp.TCPConnector(family=socket.AF_INET6 if cls.ipv6 else socket.AF_INET,resolver=aiohttp.AsyncResolver())
            cls.session = aiohttp.ClientSession(connector=cls.connector, json_serialize=json.dumps)
        return cls._instance

    @classmethod
    async def close(cls):
        if hasattr(cls, 'session') and cls.session is not None:
            await cls.session.close()
        if cls._instance is not None:
            cls._instance = None

    async def make_request(self, req_json: dict):
        async with self.session.post("http://{0}:{1}".format(self.node_url, self.node_port),json=req_json, timeout=300) as resp:
            return await resp.json()

    async def account_create(self) -> str:
        account_create = {
            'action': 'account_create',
            'wallet': self.wallet_id
        }
        respjson = await self.make_request(account_create)
        if 'account' in respjson:
            return respjson['account']
        return None

    async def account_balance(self, account: str) -> dict:
        account_balance = {
            'action': 'account_balance',
            'account': account
        }
        respjson = await self.make_request(account_balance)
        if 'balance' in respjson:
            return respjson
        return None

    async def send(self, id: str, source: str, destination: str, amount: str) -> str:
        """Make transaction, return hash if successful"""
        send_action = {
            'action': 'send',
            'wallet': Config.instance().wallet,
            'source': source,
            'destination': destination,
            'amount': amount,
            'id': id
        }
        respjson = await self.make_request(send_action)
        if 'block' in respjson:
            return respjson['block']
        return None

    async def pending(self, account: str, count: int = 5) -> List[str]:
        """Return a list of pending blocks"""
        pending_action = {
            'action': 'pending',
            'account': account,
            'count': count
        }
        respjson = await self.make_request(pending_action)
        if 'blocks' in respjson:
            return respjson['blocks']
        return None

    async def receive(self, account: str, hash: str) -> str:
        """Receive a block and return hash of receive block if successful"""
        receive_action = {
            'action': 'receive',
            'wallet': Config.instance().wallet,
            'account': account,
            'block': hash
        }
        respjson = await self.make_request(receive_action)
        if 'block' in respjson:
            return respjson['block']
        return None

    async def account_info(self, account: str) -> dict:
        info_action = {
            'action': 'account_info',
            'account': account,
            'representative': True
        }
        respjson = await self.make_request(info_action)
        if 'error' not in respjson:
            return respjson
        return None

    async def account_representative_set(self, account: str, rep: str) -> str:
        rep_action = {
            "action": "account_representative_set",
            "wallet": Config.instance().wallet,
            "account": account,
            "representative": rep
        }
        respjson = await self.make_request(rep_action)
        if 'block' in respjson:
            return respjson['block']
        return None

    async def block_count(self) -> Tuple[int, int]:
        "Returns block_count from the node as a tuple count, unchecked"
        count_action = {
            "action": "block_count"
        }
        respjson = await self.make_request(count_action)
        if 'count' in respjson and 'unchecked' in respjson:
            return int(respjson['count']), int(respjson['unchecked'])
        return None, None