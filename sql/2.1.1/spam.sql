alter table user add column last_random datetime;
alter table user add column last_favorites datetime;
update user set last_random=current_timestamp,last_favorites=current_timestamp;
