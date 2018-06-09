import db

with db.db.connection_context():
	ts = db.Transaction.select().where((db.Transaction.processed == False) & (db.Transaction.giveawayid == 0) & (db.Transaction.attempts < 3))

	for t in ts:
		print("replayed {0}".format(t.uid))
		db.process_transaction(t)
