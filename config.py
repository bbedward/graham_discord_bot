from dotenv import load_dotenv
load_dotenv()

import argparse
import pathlib
import os
import yaml
from typing import List, Tuple
from util.env import Env
from util.util import Utils
from version import __version__

class Config(object):
    _instance = None

    def __init__(self):
        raise RuntimeError('Call instance() instead')

    @classmethod
    def instance(cls) -> 'Config':
        if cls._instance is None:
            cls._instance = cls.__new__(cls)
            try:
                with open(f"{Utils.get_project_root().joinpath(pathlib.PurePath('config.yaml'))}", "r") as in_yaml:
                    cls.yaml = yaml.load(in_yaml, Loader=yaml.FullLoader)
            except FileNotFoundError:
                cls.yaml = None
            parser = argparse.ArgumentParser(description=f"Graham {'BANANO' if Env.banano() else 'Nano'} Discord Bot v{__version__}")
            parser.add_argument('-p', '--prefix', type=str, help='Command prefix for bot commands', default='!')
            parser.add_argument('-l', '--log-file', type=str, help='Log file location', default='/tmp/graham_bot.log')
            parser.add_argument('-s', '--status', type=str, help="The bot's 'playing status'", default=None, required=False)
            parser.add_argument('-u', '--node-url', type=str, help='URL of the node', default='[::1]')
            parser.add_argument('-np', '--node-port', type=int, help='Port of the node', default=7072 if Env.banano() else 7076)
            parser.add_argument('--debug', action='store_true', help='Runs in debug mode if specified', default=False)
            options, unknown = parser.parse_known_args()

            # Parse options
            cls.command_prefix = options.prefix
            if len(cls.command_prefix) != 1:
                print("Command prefix can only be 1 character")
                exit(1)
            cls.log_file = options.log_file
            cls.debug = options.debug
            cls.playing_status = f"{cls.command_prefix}help for help" if options.status is None else options.status

            cls.bot_token = os.getenv('BOT_TOKEN')
            if cls.bot_token is None:
                print("BOT_TOKEN must be set in your environment")
                exit(1)
            cls.wallet = os.getenv('WALLET_ID')
            if cls.wallet is  None:
                print("WALLET_ID must be specified in your environment")
                exit(1)

            cls.node_url = options.node_url
            cls.node_port = options.node_port
        return cls._instance

    def has_yaml(self) -> bool:
        return hasattr(self, 'yaml') and self.yaml is not None

    def get_rain_roles(self) -> List[int]:
        default = []
        if not self.has_yaml():
            return default
        elif 'restrictions' in self.yaml and 'rain_roles' in self.yaml['restrictions']:
            return self.yaml['restrictions']['rain_roles']
        return default

    def get_rain_minimum(self) -> int:
        # 1000 BAN default or 1 NANO
        default = 1000 if Env.banano() else 1
        if not self.has_yaml():
            return default
        elif 'restrictions' in self.yaml and 'rain_minimum' in self.yaml['restrictions']:
            return self.yaml['restrictions']['rain_minimum']
        return default

    def get_no_spam_channels(self) -> List[int]:
        """Get a list of channel IDs that we can't post publicly in"""
        default = []
        if not self.has_yaml():
            return default
        elif 'restrictions' in self.yaml and 'no_spam_channels' in self.yaml['restrictions']:
            return self.yaml['restrictions']['no_spam_channels']
        return default

    def get_server_info(self) -> Tuple[str, int]:
        """Returns a tuple with server host, port - or none if server is disabled"""
        default = (None, None)
        if not self.has_yaml():
            return default
        elif 'server' in self.yaml and 'host' in self.yaml['server'] and 'port' in self.yaml['server']:
            return (self.yaml['server']['host'], self.yaml['server']['port'])
        return (None, None)

    def get_admin_roles(self) -> List[int]:
        """Return a list of admin role IDs"""
        default = []
        if not self.has_yaml():
            return default
        elif 'admin' in self.yaml and 'admin_roles' in self.yaml['admin']:
            return self.yaml['admin']['admin_roles']
        return default

    def get_admin_ids(self) -> List[int]:
        """Return a list of admin user IDs"""
        default = []
        if not self.has_yaml():
            return default
        elif 'admin' in self.yaml and 'admin_ids' in self.yaml['admin']:
            return self.yaml['admin']['admin_ids']
        return default

    def get_giveaway_minimum(self) -> float:
        default = 1000 if Env.banano() else 0.25
        if not self.has_yaml():
            return default
        elif 'giveaway' in self.yaml and 'minimum' in self.yaml['giveaway']:
            return self.yaml['giveaway']['minimum']
        return default

    def get_giveaway_auto_minimum(self) -> float:
        default = 1000 if Env.banano() else 0.25
        if not self.has_yaml():
            return default
        elif 'giveaway' in self.yaml and 'minimum_auto_start' in self.yaml['giveaway']:
            return self.yaml['giveaway']['minimum_auto_start']
        return default

    def get_giveaway_auto_duration(self) -> int:
        default = 30
        if not self.has_yaml():
            return default
        elif 'giveaway' in self.yaml and 'auto_duration' in self.yaml['giveaway']:
            return self.yaml['giveaway']['auto_duration']
        return default

    def get_giveaway_no_delete_channels(self) -> List[int]:
        default = []
        if not self.has_yaml():
            return default
        elif 'giveaway' in self.yaml and 'no_delete_channels' in self.yaml['giveaway']:
            return self.yaml['giveaway']['no_delete_channels']
        return default

    def get_giveaway_auto_fee(self) -> float:
        default = 10 if Env.banano() else 0.0025
        if not self.has_yaml():
            return default
        elif 'giveaway' in self.yaml and 'auto_fee' in self.yaml['giveaway']:
            return self.yaml['giveaway']['auto_fee']
        return default

    def get_giveaway_max_fee_multiplier(self) -> float:
        default = 0.05
        if not self.has_yaml():
            return default
        elif 'giveaway' in self.yaml and 'max_fee' in self.yaml['giveaway']:
            return self.yaml['giveaway']['max_fee'] / 100
        return default

    def get_giveaway_min_duration(self) -> int:
        default = 10
        if not self.has_yaml():
            return default
        elif 'giveaway' in self.yaml and 'min_duration' in self.yaml['giveaway']:
            return int(self.yaml['giveaway']['min_duration'])
        return default

    def get_giveaway_max_duration(self) -> int:
        default = 60
        if not self.has_yaml():
            return default
        elif 'giveaway' in self.yaml and 'max_duration' in self.yaml['giveaway']:
            return int(self.yaml['giveaway']['max_duration'])
        return default

    def get_giveaway_announce_channels(self) -> List[int]:
        default = []
        if not self.has_yaml():
            return default
        elif 'giveaway' in self.yaml and 'announce_channels' in self.yaml['giveaway']:
            return self.yaml['giveaway']['announce_channels']
        return default

    def get_giveaway_roles(self) -> List[int]:
        default = []
        if not self.has_yaml():
            return default
        elif 'giveaway' in self.yaml and 'roles' in self.yaml['giveaway']:
            return self.yaml['giveaway']['roles']
        return default

    def get_no_stats_channels(self) -> List[int]:
        default = []
        if not self.has_yaml():
            return default
        elif 'restrictions' in self.yaml and 'no_stats_channels' in self.yaml['restrictions']:
            return self.yaml['restrictions']['no_stats_channels']
        return default