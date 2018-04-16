alter table user add column top_tip_day integer not null default 0;
alter table user add column top_tip_day_ts datetime;
alter table user add column top_tip_month integer not null default 0;
alter table user add column top_tip_month_ts datetime;
update user set top_tip_day=top_tip,top_tip_month=top_tip,top_tip_day_ts=top_tip_ts,top_tip_month_ts=top_tip_ts;
