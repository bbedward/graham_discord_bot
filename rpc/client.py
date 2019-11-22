import aiohttp
import ipaddress
import socket

class RPCClient():
    def __init__(self, node_url : str, node_port : int, wallet_id : str):
        self.node_url = node_url
        self.node_port = node_port
        self.wallet_id = wallet_id
        self.ipv6 = ipaddress.ip_address(node_url).version == 6
        self.conn = aiohttp.TCPConnector(family=socket.AF_INET6 if self.ipv6 else socket.AF_INET,resolver=aiohttp.AsyncResolver())

    async def make_request(self, req_json : dict):
        # TODO - re-use thiss session
        async with aiohttp.ClientSession(connector=self.conn) as session:
            async with session.post("http://{0}:{1}".format(self.node_url, self.node_port),json=req_json, timeout=300) as resp:
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