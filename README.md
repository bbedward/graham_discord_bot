# Graham (a NANO/BANANO Currency Tip Bot for Discord)

BananoBot++/Graham is an open source, free to use nano/banano bot for discord.

A few of the features included in this bot:

- standard tipping (`tip`,`tipsplit`)
- tipping all actively contributing users (`rain`)
- giveaways+raffles from individual sponsors or auto-started by the bot when pool reaches certain amount (`givearai`,`tipgiveaway`)
- individual statistics (`tipstats`)
- bot-wide statistics (`leaderboard`,`toptips`,`winners`)
- individual favorites list (`addfavorite`,`removefavorite`,`tipfavorites`,`favorites`)
- Administration commands for specific users or roles (see `adminhelp`)
- Interactive help for user friendliness

## Commands
#### For Graham(Nano Edition), replace "." with "?"
### Command Overview
- .balance
Display balance of your account

- .deposit/.register/.wallet/.address
Shows your account address

- .withdraw, takes: address (optional amount)
Allows you to withdraw from your tip account

- .ban, takes: amount <*users>
Send a tip to mentioned users

- .bansplit, takes: amount, <*users>
Split a tip among mentioned uses

- .banrandom, takes: amount
Tips a random active user

- .brain, takes: amount
Split tip among all active* users

- .givearai, takes: amount, fee=(amount), duration=(minutes)
Sponsor a giveaway

- .ticket, takes: fee (conditional)

- .tipgiveaway, takes: amount
Add to present or future giveaway prize pool

- .ticketstatus
Check if you are entered into the current giveaway

- .giveawaystats or .goldenticket
Display statistics relevant to the current giveaway

- .winners
Display previous giveaway winners

- .leaderboard/.ballers
Display the all-time tip leaderboard

- .toptips
Display largest individual tips

- .tipstats
Display your personal tipping stats

- .addfavorite, takes: *users
Add users to your favorites list

- .removefavorite, takes: *users or favorite ID
Removes users from your favorites list

- .favorites
View your favorites list

- .banfavorites, takes: amount
Tip your entire favorites list

- .mute, takes: user id
Block tip notifications when sent by this user

- .unmute, takes: user id
Unblock tip notificaitons sent by this user

- .muted
View list of users you have muted

### Account Commands

.balance
Displays the balance of your tip account (in BANANO) as described:
Actual Balance: The actual balance in your tip account
Available Balance: The balance you are able to tip with (Actual - Pending Send)
Pending Send: Tips you have sent, but have not yet been broadcasted to network
Pending Receipt: Tips that have been sent to you, but have not yet been pocketed by the node. 
Pending funds will be available for tip/withdraw after they have been pocketed by the node

.deposit/.register/.wallet/.address
Displays your tip bot account address along with a QR code
- Send NANO to this address to increase your tip bot balance
- If you do not have a tip bot account yet, this command will create one for you (receiving a tip automatically creates an account too)

.withdraw, takes: address (optional amount)
Withdraws specified amount to specified address, if amount isn't specified your entire tip account balance will be withdrawn
Example: .withdraw xrb_1111111111111111111111111111111154651111111111111111hifc8npp 1000 - Withdraws 1000 BANANO

### Tipping Commands

.ban, takes: amount <*users>
Tip specified amount to mentioned user(s) (minimum tip is 1 BANANO)
The recipient(s) will be notified of your tip via private message
Successful tips will be deducted from your available balance immediately
Example: .ban 2 @user1 @user2 would send 2 to user1 and 2 to user2

.bansplit, takes: amount, <*users>
Distributes a tip evenly to all mentioned users.
Example: .bansplit 2 @user1 @user2 would send 1 to user1 and 1 to user2

.banrandom, takes: amount
Tips amount to a random active user. Active user list picked using same logic as rain
Minimum banrandom amount: 10 BANANO

.brain, takes: amount
Distribute <amount> evenly to users who are eligible.
Eligibility is determined based on your recent activity and contributions to public channels. Several factors are considered in picking who receives rain. If you aren't receiving it, you aren't contributing enough or your contributions are low-quality/spammy.
Note: Users who have a status of 'offline' or 'do not disturb' do not receive rain.
Example: .rain 1000 - distributes 1000 evenly to eligible users (similar to tipsplit)
Minimum rain amount: 1500 BANANO

.tipauthor, takes: amount
Donate to the author of this bot

### Giveaway Commands
The different ways to interact with the bot's giveaway functionality
.givearai, takes: amount, fee=(amount), duration=(minutes)
Start a giveaway with given amount, entry fee, and duration.
Entry fees are added to the total prize pool
Giveaway will end and choose random winner after (duration)
Example: .giveaway 1000 fee=5 duration=30 - Starts a giveaway of 1000, with fee of 5, duration of 30 minutes
Minimum required to sponsor a giveaway: 1000 BANANO
Minimum giveaway duration: 5 minutes
Maximum giveaway duration: 60 minutes

.ticket, takes: fee (conditional)
Enter the current giveaway, if there is one. Takes (fee) as argument only if there's an entry fee.
 Fee will go towards the prize pool and be deducted from your available balance immediately
Example: .ticket (to enter a giveaway without a fee), .ticket 10 (to enter a giveaway with a fee of 10)

.tipgiveaway, takes: amount
Add <amount> to the current giveaway pool
If there is no giveaway, one will be started when minimum is reached.
Tips >= 10 BANANO automatically enter you for giveaways sponsored by the community.
Donations count towards the next giveaways entry fee
Example: .tipgiveaway 1000 - Adds 1000 to giveaway pool

.ticketstatus
Check if you are entered into the current giveaway
  
  
### Statistics Commands
Individual, bot-wide, and giveaway stats
.giveawaystats or .goldenticket
Display statistics relevant to the current giveaway

.winners
Display previous giveaway winners

.leaderboard or .ballers
Display the all-time tip leaderboard

.toptips
Display the single largest tips for the past 24 hours, current month, and all time

.tipstats
Display your personal tipping stats (rank, total tipped, and average tip)

### Favorites Commands
How to interact with your favorites list
.addfavorite, takes: *users
Adds mentioned users to your favorites list.
Example: .addfavorite @user1 @user2 @user3 - Adds user1,user2,user3 to your favorites

.removefavorite, takes: *users or favorite ID
Removes users from your favorites list. You can either @mention the user in a public channel or use the ID in your favorites list
Example 1: .removefavorite @user1 @user2 - Removes user1 and user2 from your favorites
Example 2: .removefavorite 1 6 3 - Removes favorites with ID : 1, 6, and 3

.favorites
View your favorites list. Use .addfavorite to add favorites to your list and .removefavorite to remove favories

.banfavorites, takes: amount
Tip everybody in your favorites list specified amount
Example: .banfavorites 1000 Distributes 1000 to your entire favorites list (similar to .bansplit)

### Notification Settings
Handle how tip bot gives you notifications
.mute, takes: user id
When someone is spamming you with tips and you can't take it anymore

.unmute, takes: user id
When the spam is over and you want to know they still love you

.muted
Are you really gonna drunk dial?


## About

Graham is designed so that every tip is a real transaction on the NANO/BANANO network.

Some highlights:

- Transactions are queued and processed synchronously in a worker thread, while bot activity is handled in a main thread
- User data, transactions, and all other persisted data is stored using the Peewee ORM with Sqlite
- Operates with a single NANO/BANANO wallet, with 1 account per user

Recommend using with a GPU/OpenCL configured node (or work peer) on busier discord servers due to POW calculation.

## Getting started

1) These instructions are pretty rough, if someone wants to make wiki entries or PRs to improve them be my guest

2) Instructions assume ubuntu 18.04 or greater. Any debian-based distribution should work with these as long as you have python 3.6+ (3.5 will NOT work)

3) Yes, it's possible to run on centOS or gentoo or arch or slackware or windows or OSX or whateva you want. But that's up to you to figure out, i dont rly want to tech support and troubleshoot other installations

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

### Contribute
"Lorem ipsum carrots, enhanced undergraduate developer, but they do occaecat time and vitality, such as labor and obesity. Over the years come, who nostrud exercise, the school district work unless they aliquip advantage from it. Homework if cupidatat consumer to find pleasure wants to be a football cillum he shuns pain, produces no resultant. Excepteur cupidatat blacks are not excepteur, is soothing to the soul, that is, they deserted the general duties of those who are to blame for your troubles. " 

### Reviews
Graham v3.1.1 (BANANO Edition) - by bbedward
Reviews:
'10/10 True Masterpiece' - That one guy

'0/10 Didn't get rain' - Almost everybody else

'8/10' imroved readme - Computer_Genius

This bot is completely free to use and open source. Developed by bbedward (reddit: /u/bbedward, discord: bbedward#9246)
Feel free to send tips, suggestions, and feedback.

Consider using this node as a representative to help decentralize the network!
Representative Address: ban_354zikbhgyufnnc98kp4h5w1jmpd1ngiwjo63e7aoz837wmtx3pjxjczq68x

github: https://github.com/bbedward/Graham_Nano_Tip_Bot
