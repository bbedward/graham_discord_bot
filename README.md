# Graham (a NANO/BANANO Currency Tip Bot for Discord)

Graham/BananoBot++ is an open source, free to use nano/banano bot for discord.

You can see/use a NANO and BANANO instance of this bot on the [official banano discord](https://chat.banano.co.in)

## Features


## Commands
#### For Graham(Nano Edition), replace . with ?


### Commmand Overview
- `balance` : Display balance of your accou

- `deposit` or `register` or `wallet` or `address` : Shows account address, or creates one if it doesn't yet exist

- `withdraw`, takes: address (optional amount) : Allows you to withdraw from your tip account

- `tip` (NANO) or `ban` (BANANO), takes: amount <*users> : Send a tip to mentioned users

- `tipsplit` (NANO) or `bansplit` (BANANO), takes: amount, <*users> : Split a tip among mentioned uses

- `tiprandom` (NANO) or `banrandom` (BANANO) takes: amount : Tips a random active user

- `rain` (NANO) or `brain` (BANANO), takes: amount : Split tip among all active* users

- `giveaway`, takes: amount, fee=(amount), duration=(minutes) : Sponsor a giveaway

- `ticket`, takes: fee (conditional) : Enter the active giveaway

- `tipgiveaway`, takes: amount : Add to present or future giveaway prize pool

- `ticketstatus` : Check if you are entered into the current giveaway

- `giveawaystats` or `goldenticket` : Display statistics relevant to the current giveaway

- `winners` : Display previous giveaway winners

- `leaderboard` or `ballers` : Display the all-time tip leaderboard

- `toptips` : Display largest individual tips

- `tipstats` : Display your personal tipping stat

- `addfavorite`, takes: *users : Add users to your favorites list

- `removefavorite`, takes: *users or favorite ID : Removes users from your favorites list

- `favorites` : View your favorites list

- `tipfavorites` (NANO) or `banfavorites` (BANANO), takes: amount : Tip your entire favorites list

- `mute`, takes: user id : Block tip notifications when sent by this user

- `unmute`, takes: user id : Unblock tip notificaitons sent by this user

- `muted` : View list of users you have muted

- `adminhelp` : View list of available admin commands (For users with admin privileges, configured in settings.py)


## About

Graham is designed so that every tip is a real transaction on the NANO/BANANO network.

Some highlights:

- All bot-related activity including creating transactions is handled in the primary bot process, asynchronously
- Actual transaction processing is handled by celery worker processes 'graham_backend' (RPC Send/RPC Receive)
- Communication between the bot and worker processes is done using redis
- User data, transactions, and all other persisted data is stored using the Peewee ORM with PostgreSQL
- Operates with a single NANO/BANANO wallet, with 1 account per user

Recommend using with a GPU/OpenCL configured node (or work peer) on busier discord servers due to POW calculation.

# Setting up your own bot

Instructions assume a debian-based installation with python3.6 installed.

The bot will run on any linux distribution with python 3.6 or greater, mac, or windows. If you get it setup on windows consider documenting it and I'll add the steps to the wiki.

## Requirements

```
sudo apt install python3.6 python3.6-dev libcurl4-openssl-dev git redis-server postgresql
```

(Optional - to run with pm2)

```
sudo apt install npm nodejs
sudo npm install -g pm2
```

### Setting up a node

There are many ways to setup a nano/banano node. From simply using the desktop wallet to building from source to using docker.

Here's some resources on [setting up a NANO node](https://1nano.co/support-the-network/) and [setting up a BANANO node](https://github.com/BananoCoin/banano/wiki):

The NANO/BANANO discords are the best places to go for support if you get stuck or need help.

### 1. Cloning the repository

```
cd ~
git clone https://github.com/bbedward/Graham_Nano_Tip_Bot.git graham
```

### 2. Setting up a PostgreSQL database and user

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

### 3. Create wallet for tip bot

Note: substitute rai_node with bananode for banano

```
docker <container_id> exec rai_node --wallet_create
```

non-docker nodes:

```
/path/to/rai_node --wallet_create
```

This will output your wallet ID (NOT the seed), copy this as you will need it for later

To backup the seed:

```
rai_node --wallet_decrypt_unsafe --wallet=<ID>
```

### 4. Discord bot

Create discord bot and get client ID and token (also save both of these for the next step)

Guide written by somebody else https://github.com/reactiflux/discord-irc/wiki/Creating-a-discord-bot-&-getting-a-token

### 5. Configuration

```
cd graham
cp settings.py.example settings.py
```

Edit settings.py with any text editor, e.g. `nano settings.py` and configure it as follows:

```
discord_bot_id = 'YOUR_DISCORD_CLIENT_ID_HERE'
discord_bot_token = 'YOUR_DISCORD_BOT_TOKEN_HERE'
wallet = 'YOUR_WALLET_ID_RETURNED_FROM_NODE'
```

Also configure the postgres connection info from before:

```
database='graham'
database_user='tipbot_user'
database_password='mypassword'
```

and if you are using the bot for BANANO and not NANO then set:

```
banano=True
```

### 6. Setting up virtual environment and python requirements

```
virtualenv -p python3.6 venv
source venv/bin/activate
pip install -r requirements.txt
```

That's it, if configured correctly you can run the bot.

## Running with PM2

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

## Running normally

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

## CLI tool

There's a CLI utility for certain functions (looking up block hashes, replaying unprocessed transactions, etc)

You can see features available by

```
cli.py -h
```

# Graham 2.5 -> 3.0+ upgrade instructions

First stop the bot completely, git pull, and install pre-reqs:

```
sudo apt install redis-server postgresql ruby ruby-dev libsqlite3-dev libpq-dev
```

```
sudo gem install sequel pg sqlite3
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
sudo sequel -C sqlite://nanotipbot.db postgresql://graham_user:password@localhost:5432/graham
```

If all went well , run the post-migrate

Use database name as argument from above (graham or whatever you used):

```
sudo -u postgres ./sql/3.0/post_migrate.sh graham_user password graham
```

??? profit

If you have issues migrating contact me and i'll help if I'm available


### Reviews

Graham v3.1.1 (BANANO Edition) - by bbedward
Reviews:
'10/10 True Masterpiece' - That one guy

'0/10 Didn't get rain' - Almost everybody else

'8/10' imroved readme - Computer_Genius

This bot is completely free to use and open source. Developed by bbedward (reddit: /u/bbedward, discord: bbedward#9246)
Feel free to send tips, suggestions, and feedback.

# Contribute

I created and operate Graham for free, and I am cool with that.

If you'd like to buy me a beer though it's always appreciated:

`xrb_1hmefcfq35td5f6rkh15hbpr4bkkhyyhmfhm7511jaka811bfp17xhkboyxo`

or banano

`ban_1ykrq6ejzni5duexqtekhewfk8aeebrgsjtqacbu4okoddj33ee3yzffib1k`





-