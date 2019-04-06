
from gevent import monkey
monkey.patch_all()

import datetime

from flask import Flask, g, jsonify
from peewee import DoesNotExist

from db import User, db

# create a flask application - this ``app`` object will be used to handle
# inbound requests, routing them to the proper 'view' functions, etc
app = Flask(__name__)
app.config.from_object(__name__)

# Request handlers -- these two hooks are provided by flask and we will use them
# to create and tear down a database connection on each request.
@app.before_request
def before_request():
    g.db = db
    g.db.connect()

@app.after_request
def after_request(response):
    g.db.close()
    return response

@app.route('/ufw/<address>', methods=['GET'])
def ufw(address : str):
    try:
        user = User.select().where(User.wallet_address == address).get()
        return jsonify({
            'discord_id':user.user_id,
            'user_name':user.user_name,
            'created_ts': format_js_iso(user.created)
        })
    except User.DoesNotExist:
        return jsonify({'error':'user does not exist'})

def format_js_iso(date):
    """Format a time to ISO string format for javascript"""
    return datetime.datetime.strftime(date, '%Y-%m-%dT%H:%M:%S.{0}Z').format(int(round(date.microsecond / 1000.0)))

# allow running from the command line
#if __name__ == '__main__':
#    app.run()