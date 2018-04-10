alter table 'transaction' add column sent integer default 0; update 'transaction' set 
sent=1,processed=1 where giveawayid == 0; update user set pending_send=0,pending_receive=0; 
update giveaway set active=0; delete from contestant;
delete from 'transaction' where giveawayid<>0;
