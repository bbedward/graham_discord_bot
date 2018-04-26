import db
import settings
import wallet

'''Script I whipped up to change reps for every account registered with the bot, it iterate the array of reps repeatedly and set them for each account'''

reps = [ "xrb_1i9ugg14c5sph67z4st9xk8xatz59xntofqpbagaihctg6ngog1f45mwoa54",
            "xrb_1x7biz69cem95oo7gxkrw6kzhfywq4x5dupw4z1bdzkb74dk9kpxwzjbdhhs",
            "xrb_3x7cjioqahgs5ppheys6prpqtb4rdknked83chf97bot1unrbdkaux37t31b",
            "xrb_1jeqoxg7cpo5xgyxhcwzsndeuqp6yyr9m63k8tfu9mskjdfo7iq95p1ktb8j",
            "xrb_1ninja7rh37ehfp9utkor5ixmxyg8kme8fnzc4zty145ibch8kf5jwpnzr3r",
            "xrb_3hrppx3sfxoiycjm9iaqsr3odecgarcxxxhsm41s9pbs75ykambxqhu9ys58"]

def change_reps():
	accts = db.get_accounts()
	idx = 0
	for x in accts:
		if idx > len(reps) - 1:
			idx = 0
		rep = reps[idx]
		idx += 1
		check = {'action':'account_representative','account':x}
		output = wallet.communicate_wallet(check)
		if 'representative' not in output or output['representative'] not in reps:
			print("Setting REP: {0} for ACCT: {1}".format(rep, x))
			action = {'action':'account_representative_set', 'wallet':settings.wallet, 'account':x, 'representative':rep}
			wallet.communicate_wallet(action)
		else:
			print("Acct: {0} already set".format(x))

change_reps()
