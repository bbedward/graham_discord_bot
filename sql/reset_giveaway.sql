update giveaway set active=0;
delete from contestant;
/*update user as u set u.pending_send=(u.pending_send - cast(t.amount as integer)) inner join 'transaction' as t on t.source_address = u.wallet_address where t.giveawayid <> 0;*/
delete from 'transaction' where giveawayid<>0;
