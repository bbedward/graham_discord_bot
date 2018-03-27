#!/bin/bash

db=${1}
user=${2}
pass=${3}


curl -F files[]=@nanotipbot.db https://www.rebasedata.com/api/v1/convert?outputFormat=mysql -o output.zip
unzip output.zip
rm -f output.zip

mysql -h "localhost" -u "${2}" "-p${3}" "${1}" < data.sql
mysql -h "localhost" -u "${2}" "-p${3}" "${1}" -e "update user set tipped_amount=0;update user set tip_count=0; alter table user modify pending_receive int(20); alter table user modify pending_send int(20); alter table user modify tipped_amount decimal(30,6); update transaction set processed=1; update user set pending_receive=0; update user set pending_send=0;"
