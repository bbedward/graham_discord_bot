import argparse
import ipaddress
import sys
from rpc.client import RPCClient
from util.env import Env
from version import __version__

class Config():
    def __init__(self):
        parser = argparse.ArgumentParser(description=f"Graham NANO/BANANO TipBot v{__version__}")
        parser.add_argument('-p', '--prefix', type=str, help='Command prefix for bot commands', default='!')
        parser.add_argument('-l', '--log-file', type=str, help='Log file location', default='/tmp/graham_tipbot.log')
        parser.add_argument('-s', '--status', type=str, help="The bot's 'playing status'", default=None, required=False)
        parser.add_argument('-t', '--token', type=str, help='Discord bot token', required=True)
        parser.add_argument('-u', '--node-url', type=str, help='URL of the node', required=True, default='[::1]')
        parser.add_argument('-np', '--node-port', type=int, help='Port of the node', required=True, default=7072 if Env.banano() else 7076)
        parser.add_argument('-w', '--wallet', type=str, help='ID of the wallet to use on the node/wallet server', required=True)
        parser.add_argument('--debug', action='store_true', help='Runs in debug mode if specified', default=False)
        options = parser.parse_args()

        # Parse options
        self.command_prefix = options.prefix
        if len(self.command_prefix) != 1:
            print("Command prefix can only be 1 character")
            sys.exit(1)
        self.log_file = options.log_file
        self.debug = options.debug
        self.playing_status = f"{self.command_prefix}help for help" if options.status is None else options.status
        self.bot_token = options.token
        self.wallet = options.wallet

        try:
            self.node_url = str(ipaddress.ip_address(options.node_url))
        except ValueError:
            print("Node URL is invalid")
            sys.exit(1)
        self.node_port = options.node_port

        self.rpc = RPCClient(
            self.node_url,
            self.node_port,
            self.wallet
        )