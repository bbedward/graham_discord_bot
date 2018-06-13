# Graham (a NANO/BANANO currency Tip Bot for Discord)

Graham is an open source, free to use nano bot for discord.

A few of the features included in this bot:

- standard tipping (`tip`,`tipsplit`)
- tipping all actively contributing users (`rain`)
- giveaways+raffles from individual sponsors or auto-started by the bot when pool reaches certain amount (`givearai`,`tipgiveaway`)
- individual statistics (`tipstats`)
- bot-wide statistics (`leaderboard`,`toptips`,`winners`)
- individual favorites list (`addfavorite`,`removefavorite`,`tipfavorites`,`favorites`)
- Administration commands for specific users or roles (see `adminhelp`)
- Interactive help for user friendly-ness

And much more than listed here probably

## About

Graham is designed so that every tip is a real transaction on the NANO network.

Some highlights:

- Transactions are queued and processed synchronously in a worker thread, while bot activity is handled in a main thread.
- User data, transactions, and all other persisted data is stored using the Peewee ORM with Sqlite
- Operates with a single NANO wallet, with 1 account per user

Recommend using with a GPU/OpenCL configured node (or work peer) on busier discord servers due to POW calculation.

## Getting started

1) These instructions are pretty rough, if someone wants to make wiki entries or PRs to improve them b my guest

2) Instructions assume ubuntu 18.04 or greater. Any debian-based distribution should work with these as long as you have python 3.6+ (3.5 will NOT work)

3) Yea it's possible to run on centOS or gentoo or arch or slackware or windows or OSX or whateva you want. But that's up to you to figure out, i dont rly want to tech support and troubleshoot other installations

### Requirements

```
sudo apt install python3 python3-dev libcurl4-openssl-dev git redis-server postgresql
```

(Optional - to run with pm2)

```
sudo apt install npm nodejs
sudo npm install -g pm2
```

Note: python 3.6+ is required. On older distributions you may need to source a third party package.

### Cloning

```
cd ~
git clone https://github.com/bbedward/Graham_Nano_Tip_Bot.git nanotipbot
```

### Setting up a PostgreSQL database and user

Use:
```
sudo -u postgres psql
```
To open a postgres prompt as the `postgres` user.

```
create role tipbot_user with login password 'mypassword';
```
Use whatever username and password you want, you will need to remember the postgres username `tipbot_user` and password `mypassword` for later tip bot configuration.

```
create database graham;
grant all privileges on database graham to tipbot_user;
```
Creates a database `graham` and grants privileges on that database to `tipbot_user`

so our bot settings under this example look like:

```
database='graham'
database_user='tipbot_user'
database_password='mypassword'
```

### Set up BA/NANO Node

You can follow the lovely guide here for setting up a docker nano node if you don't already have one running:

https://1nano.co/support-the-network/

Banano:

https://github.com/BananoCoin/banano/wiki

You need rpc_enable and enable_control set to 'true' in the config.json

### Create wallet for tip bot

Note: substitute rai_node with bananode for banano

```
docker <container_id> exec rai_node --wallet_create
```

non-docker nodes:

```
/path/to/rai_node --wallet_create
```

This will output your wallet ID (NOT the seed), copy this as you will need it for later

### Discord bot

Create discord bot and get client ID and token (also save both of these for the next step)

Guide written by somebody else https://github.com/reactiflux/discord-irc/wiki/Creating-a-discord-bot-&-getting-a-token

### Configuration

```
cd nanotipbot
cp settings.py.example settings.py
```

Then open settings.py with any text editor and add your bot's client ID, token, and the wallet ID from earlier

set banano=True for banano

Also you will need the postgres database name, user, and password from earlier

### Virtualenv + python requirements

```
virtualenv -p python3.6 venv
source venv/bin/activate
pip install -r requirements.txt
```

### Running with PM2

Bot:
```
pm2 start graham_bot.sh
pm2 save
```

Backend/TX Processor:
```
pm2 start graham_backend.sh
pm2 save
```

You can view logs under ~/.pm2/logs/

e.g.: `tail -f ~/.pm2/logs/graham-bot-error-0.log` to follow the bot logs

or

`tail -f ~/.pm2/logs/graham-backend-error-0.log` to follow the worker logs`

### Running normally

```
./graham_bot.sh
```

or in background:

```
nohup ./graham_bot.sh &
```

Backend:

```
./graham_backend.sh
```

or in background:

```
nohup ./graham_backend.sh &
```

# Graham 2.5 -> 3.0 migration path


First stop the bot completely, git pull, and install pre-reqs:

```
apt install redis-server postgresql pgloader
```

and python pre-reqs:

```
./venv/bin/pip install -U -r requirements.txt
```

Backup anything you fear may be lost

Run migration pre-reqs on old table

```
sqlite3 nanotipbot.db < sql/3.0/migrate.sql
```

Create database/user/password for postgres

```
sudo -u postgres psql
```

in  postgres prompt:

```
create database graham;
create role graham_user with login password 'password';
grant all privileges on database graham to graham_user;
\q
```

**Note the username, password, and database name used here**

In this example they are:

```
database: 'graham'
user: 'graham_user'
password: 'password'
```

Substitute the values below with yours if they are different

Run the migration:
```
sudo cp nanotipbot.db /var/lib/postgresql
sudo chown postgres:postgres /var/lib/postgresql/nanotipbot.db
sudo -u postgres pgloader /var/lib/postgresql/nanotipbot.db postgresql://graham_user:password@localhost:5432/graham
```

If all went well , run the post-migrate

Use database name as argument from above (graham or whatever you used):

```
sudo -u postgres ./sql/3.0/post_migrate.sh graham_user password graham
```

??? profit

If you have issues migrating contact me and i'll help if I'm availabl
