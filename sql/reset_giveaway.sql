update giveaway set active=0;
delete from contestant;
delete from 'transaction' where giveawayid=-1;
