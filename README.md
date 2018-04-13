# Graham (a NANO currency Tip Bot for Discord)

Graham is an open source, free to use nano tip bot for discord.

A few of the features included in this bot:

- standard tipping (`tip`,`tipsplit`)
- tipping all actively contributing users (`rain`)
- giveaways+raffles from individual sponsors or auto-started by the bot when pool reaches certain amount (`givearai`,`tipgiveaway`)
- individual statistics (`tipstats`)
- bot-wide statistics (`leaderboard`,`toptips`,`winners`)
- individual favorites list (`addfavorite`,`removefavorite`,`tipfavorites`)
- Administration commands for specific users or roles (`tipban`/`tipunban`, `statsban/statsunban`, `settiptotal/settipcount`, `pause/unpause`)

## About

Graham is designed so that every tip is a real transaction on the NANO network.

Some highlights:

- Transactions are queued and processed synchronously in a worker thread, while bot activity is handled in a main thread.
- User data, transactions, and all other persisted data is stored using the Peewee ORM with Sqlite
- Operates with a single NANO wallet, with 1 account per user

Recommend using with a GPU/OpenCL configured node (or work peer) on busier discord servers due to POW calculation.

## Usage

To run the bot, update `settings.py` with nano wallet ID and discord bot ID+Token, then simply use:

```
python3 bot.py
```

or to run in background

```
nohup python3 bot.py &
```

Optionally update `scripts/reboot_node.sh` with commands you would like automatically executed when tip bot encounters timeouts when doing RPC sends.

** WARNING **

There exists a script in scripts/cron called `nanotipbotbackup`. Highly recommend you use this or something better to backup the tip bot database.

Simply toss the script in cron.hourly, crontab, cron.daily, whatever - and update the backup path and database path.

## Dependencies (install using pip)

- Python 3.5+
- NANO Node v10+ (see: https://github.com/nanocurrency/raiblocks/wiki/Docker-node)
- SQLite
- `discord.py 1.0+ (rewrite)`
- `peewee`
- `asyncio`
- `pycurl`

## Graham 2.0 Update

Graham 2.0 switched to the rewritten discord.py API (discord.py 1.0.0)

You can install this using:

`pip3 install -U git+https://github.com/Rapptz/discord.py@rewrite#egg-discord.py[voice]`

