alter table user add column last_msg_rain datetime;
update user set last_msg_rain=current_timestamp;
