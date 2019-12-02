
# Graham - Discord Bot for BANANO and NANO

  

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

  

Installing these requirements is dependent on your operating system, you should be able to find out how to install them quickly with a simple google search, example: "How to intall python 3.7 on ubuntu 18.04", "how to install python 3.7 on MacOS catalina"

  

## PostgreSQL or SQLite?

  

You can use PostgreSQL or SQLite with Graham. SQLite is an easier to setup and more portable solution (easier to copy the database to different machines, etc.), but it's potentially more prone to corruption, less performant, etc.

  

TODO - i haven't added support for Postgres yet

  

## Configuring the bot

  

There are 3 different ways to configure different things.

  

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