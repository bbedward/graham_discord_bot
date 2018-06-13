#!/bin/bash
psql postgresql://${1}:${2}@localhost:5432/${3} << EOF
	alter table users alter column stats_ban drop default;
	alter table users alter stats_ban type bool using stats_ban::int::boolean;
	alter table users alter column stats_ban set default false;
	alter table transactions alter column processed drop default;
	alter table transactions alter processed type bool using processed::int::boolean;
	alter table transactions alter column processed set default false;
	alter table giveaway alter active type bool using active::int::boolean;
	alter table contestant alter banned type bool using banned::int::boolean;
EOF

