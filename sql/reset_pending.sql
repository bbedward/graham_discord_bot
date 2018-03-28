/* Clears all pending tips and transactions, unprocessed tips will go back to available balances*/
update user set pending_send=0,pending_receive=0;
update 'transaction' set processed=1;
update 'transaction' set giveawayid=0 where giveawayid=-1;
