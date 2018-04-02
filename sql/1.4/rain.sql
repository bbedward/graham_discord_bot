CREATE UNIQUE INDEX ux_user_id ON user(user_id);
alter table user add column last_msg_count integer default 0 ;
