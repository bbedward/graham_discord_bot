
from gevent import monkey
monkey.patch_all()
import psycogreen.gevent
psycogreen.gevent.patch_psycopg()

import datetime
import redis
import json

from flask import Flask, g, jsonify, request, abort
from peewee import DoesNotExist

from db import User, db

rd = redis.Redis()

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
            'created_ts': format_js_iso(user.created),
        })
    except User.DoesNotExist:
        return jsonify({'error':'user does not exist'})

@app.route('/ufwlist/', methods=['POST'])
def ufwlist():
    json_list = request.get_json(silent=True)
    if json_list is None:
        abort(400, 'bad request - expected json payload')
    elif not isinstance(json_list, list):
        abort(400, 'bad request - expected a list')
    ret = []
    for user in User.select().where(User.wallet_address.in_(json_list)):
        ret.append({
            'discord_id':user.user_id,
            'user_name':user.user_name,
            'created_ts': format_js_iso(user.created),
        })
    return jsonify(ret)

@app.route('/users', methods=['GET'])
def get_users():
    """Get users, but cache result for 10 minutes"""
    cache_key = 'GRAHAM_API_CACHED_USERS'
    cached = rd.get(cache_key)
    if cached is not None:
        return jsonify(json.loads(cached.decode('utf-8')))
    ret = []
    for user in User.select():
        ret.append({
            'discord_id':user.user_id,
            'user_name':user.user_name,
            'created_ts': format_js_iso(user.created),
        })
    rd.set(cache_key, json.dumps(ret), ex=600)
    return jsonify(ret)

def format_js_iso(date):
    """Format a time to ISO string format for javascript"""
    return datetime.datetime.strftime(date, '%Y-%m-%dT%H:%M:%S.{0}Z').format(int(round(date.microsecond / 1000.0)))

# allow running from the command line
#if __name__ == '__main__':
#    app.run()