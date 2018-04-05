#!/bin/bash
echo "Normal: $(sqlite3 nanotipbot.db < sql/get_pending.sql)"
echo "Giveaway: $(sqlite3 nanotipbot.db < sql/get_pending_giveaway.sql)"
