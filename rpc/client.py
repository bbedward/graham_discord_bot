import logging
import aiohttp
import rapidjson as json
import socket
import os
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
            cls.wallet_id = Config.instance().wallet
            cls.node_url = Config.instance().node_url
            cls.session = aiohttp.ClientSession(json_serialize=json.dumps)
            cls.bpow_key = os.getenv('BPOW_KEY', None)
            cls.logger = logging.getLogger('RPCClient')
        return cls._instance

    @classmethod
    async def close(cls):
        if hasattr(cls, 'session') and cls.session is not None:
            await cls.session.close()
        if cls._instance is not None:
            cls._instance = None

    async def make_request(self, req_json: dict):
        async with self.session.post(self.node_url ,json=req_json, timeout=300) as resp:
            respJson = await resp.json()
            if resp.status != 200:
                self.logger.error(f"RPC request failed with status {resp.status}")
                self.logger.error(f"Request: {req_json}")
                self.logger.error(f"Response: {respJson}")
            return respJson

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
        if self.bpow_key is not None:
            send_action['bpow_key'] = self.bpow_key
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
        if self.bpow_key is not None:
            receive_action['bpow_key'] = self.bpow_key
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
        if self.bpow_key is not None:
            rep_action['bpow_key'] = self.bpow_key
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