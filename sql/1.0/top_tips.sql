alter table user add column top_tip text;
alter table user add column top_tip_ts datetime;
update user set top_tip=cast((select MAX(cast(t.amount as integer)) from 'transaction' as t where (t.source_address = wallet_address) and (t.to_address not in(select wallet_address from user))) as text);
update user set top_tip_ts=(select t.created from 'transaction' as t where (t.source_address = wallet_address) and (t.to_address not in(select wallet_address from user)));
update user set top_tip = '0' where top_tip is null;
update user set top_tip_ts = current_timestamp where top_tip_ts is null;
