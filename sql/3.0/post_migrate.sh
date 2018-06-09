#!/bin/bash
psql postgresql:///${1} << EOF
	alter table users alter column stats_ban drop default;
	alter table users alter stats_ban type bool using stats_ban::int::boolean;
	alter table users alter column stats_ban set default false;
	alter table transactions alter column processed drop default;
	alter table transactions alter processed type bool using processed::int::boolean;
	alter table transactions alter column processed set default false;
	alter table giveaway alter active type bool using active::int::boolean;
	alter table contestant alter banned type bool using banned::int::boolean;
	alter table users alter created type timestamp using created ;
	alter table users alter last_msg type timestamp using last_msg ;
	alter table users alter last_msg_rain type timestamp using last_msg_rain ;
	alter table users alter top_tip_ts type timestamp using top_tip_ts ;
	alter table users alter top_tip_month_ts type timestamp using top_tip_month_ts ;
	alter table users alter top_tip_day_ts type timestamp using top_tip_day_ts ;
	alter table users alter last_withdraw type timestamp using last_withdraw ;
	alter table users alter last_random type timestamp using last_random ;
	alter table users alter last_favorites type timestamp using last_favorites ;
	alter table transactions alter created type timestamp using created ;
	alter table giveaway alter end_time type timestamp using end_time ;
	alter table userfavorite alter created type timestamp using created ;
	alter table mutedlist alter created type timestamp using created ;
	alter table frozenuser alter created type timestamp using created ;
# ADD ME LATER	alter table * owner (postgres_user_name)
# Change all to utcnow()
#
EOF

