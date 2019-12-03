
# Graham - Discord Bot for BANANO and NANO

[![GitHub release (latest)](https://img.shields.io/github/v/release/appditto/graham_discord_bot)](https://github.com/appditto/graham_discord_bot/releases) [![License](https://img.shields.io/github/license/appditto/graham_discord_bot)](https://github.com/appditto/graham_discord_bot/blob/master/LICENSE) [![Pipeline](https://gitlab.com/appditto/graham_discord_bot/badges/master/pipeline.svg)](https://gitlab.com/appditto/graham_discord_bot/pipelines)

Graham is the most advanced, highest performing discord bot for any cryptocurrency ever. It is built for the [BANANO](https://banano.cc) and [NANO](https://nano.org) cryptocurrencies.  

The features of this bot include on-chain tipping, rains, favorites, wide-variety of statistics, giveaways, a suite of administration commands, and more.

## Why do I want this?

Because Graham is awesome, with it you can:
- Allow users to tip each other for quality content, etc.
- Increase engagement in your discord server via features such as rains and giveaways
- Help educate people on cryptocurrencies and the value they provide

## Where can I see it in action?

Head to the [BANANO Discord](https://chat.banano.cc) - you can see both the NANO and BANANO bots in action just by typing `?help` and `.help`

## How do I add it to my server?

Graham is currently not public, but it will be soon! In the meantime you can follow the instructions below to setup your own.

# Setting up your own Graham

## Requirements

Graham 4.0+ requires the following:

- A unix environment (MacOS or Linux or WSL)
- Python 3.7+
- PostgreSQL or SQLite3
- A Redis Server/Database
- A NANO or BANANO node - [setting up a node](https://docs.nano.org/running-a-node/node-setup/). You will want to enable RPC and enable_control once your node is up and running. [node configuration](https://docs.nano.org/running-a-node/configuration/)

It sounds like a lot, but it's actually quite simple.

On ubuntu 18.04 you can get everything you need with:
```
$ sudo apt update
$ sudo apt install software-properties-common
$ sudo add-apt-repository ppa:deadsnakes/ppa
$ sudo apt install python3.7 python3.7-dev redis-server git
# And if you choose to use PostgreSQL over SQLite
$ sudo apt install postgresql
```

Installing these requirements is dependent on your operating system, you should be able to find out how to install them quickly with a simple google search, example: "How to intall python 3.7 on centos 7", "how to install python 3.7 on MacOS catalina"

## Configuring the bot

There are 3 different "groups" of settings to configure the bot.

1) **Environment**
Sensitive variables are stored in the environment. There are two environment variables that are required to run the bot. You can put this in a file called **`.env`** in the same directory as the project.
```
# The ID of the wallet the bot will use
# This is returned to you when you use `wallet_create`
WALLET_ID=1234
# Bot Token
# See here for how to obtain one:
# https://www.writebots.com/discord-bot-token/
BOT_TOKEN=1234
```

2) **Command Line Arguments**
These are all required options, but they have typical defaults already specified. Use **`python3.7 bot.py --help`** to see the full list of options.

3) **YAML Configuration File**
A file fulled of optional settings, everything in the file is optional - typically these settings tweak the bot's behavior and various thresholds. You need to create the file **`config.yaml`** with the options you want, you can see all of the available options in **`config.yaml.example`**

## PostgreSQL or SQLite?

You can use PostgreSQL or SQLite with Graham. SQLite is an easier to setup and a more portable solution (easier to copy the database to different machines, etc.), but it's potentially more prone to corruption, less performant, etc.

**Using SQLite** 
The bot will use SQLite by default and you don't have to configure anything.

**Using Postgres**

After postgres is installed

```
# Run psql as postgres user
$ sudo -u postgres psql
```
Run the following to create your database, changing `mypassword`, `user_name`, and `database_name` with whatever you want.

```
create role user_name with login password 'mypassword';
create database database_name;
grant all privileges on database database_name to user_name;
\q
```

Then add these to the `.env`, creating one if it doesn't already exist.

```
POSTGRES_DB=database_name
POSTGRES_USER=user_name
POSTGRES_PASSWORD=mypassword
```

You can also override the postgres host and port if desired with `POSTGRES_HOST` and `POSTGRES_PORT`

## Setting up callback

Create a config.yaml if it doesn't already exist, ensure the following is added to it:

```
server:
  # The host/port of the bot's aiohttp server
  # Used for callbacks and APIs
  # Callback is at $host:$port/callback (e.g. 127.0.0.1:11337/callback)
  host: 127.0.0.1
  port: 11337
```

Then in your node configuration at `~/BananoData/config-node.toml` or `~/Nano/config-node.toml` add:

```
[node.httpcallback]
address = "::ffff:127.0.0.1"
port = 11337
target = "/callback"
```

Then your bot will notify users when they make a deposit.

## Installing python dependencies

We're going to use a `virtualenv` as the environment our bot will run in.

```
# Create virtualenv
$ python3.7 -m pip install virtualenv
$ python3.7 -m virtualenv venv
$ source venv/bin/activate
# Install requirements
$ pip install -U -r requirements.txt
```

## Running the bot

Once you have configured your `.env` file you can run the bot.

```
# get a list of options you can override
$ python bot.py --help
# Run bot
$ python bot.py
```

## Installing as a service

You can run Graham as a system service if you want it to automatically start on boot.

**With systemd (Linux)**

Create the file `/etc/systemd/system/graham.service`

Add the following

```
[Unit]
Description=Graham Bot
After=network.target

[Service]
Type=simple
User=YOUR_LINUX_USER
Group=YOUR_LINUX_USER
WorkingDirectory=/home/YOUR_LINUX_USER/graham_discord_bot
EnvironmentFile=/home/YOUR_LINUX_USER/graham_discord_bot/.env
ExecStart=/home/YOUR_LINUX_USER/graham_discord_bot/venv/bin/python bot.py

[Install]
WantedBy=multi-user.target
```

Enable it to start on boot:
```
$ sudo systemctl enable graham
```

Start it:
```
$ sudo systemctl start graham
```

Check status:
```
$ sudo systemctl status graham
```

## How do I upgrade from Graham 3.0 to Graham 4.0?
Upgrading is not officially supported or documented.

If you want to attempt to update while migrating data - install a fresh Graham 4.0 first

You can then reference the script in the `v3_migrate` folder.

**The script MAY NOT fit your situation!**

It should be used as a reference, and you should modify it as necessary.