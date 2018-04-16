#!/bin/bash

# Uncomment if you want the bot to attempt to restart the node when it thinks something is wrong

#container_id=$(docker ps | grep "nanocurrency/nano" | awk '{print $1}')
#curl -g -d '{"action":"stop"}' '[::1]:7076'
#sleep 15
#docker restart $container_id
