# Changelog

## [5.0.0] - 2026-08-13

- Migrate every command from prefix messages to Discord slash commands; the Message Content privileged intent is no longer used or requested
- Startup probes which privileged intents the application has and degrades gracefully without them (HTTP member lookups, no DND suppression) instead of refusing to connect; force with GRAHAM_PRIVILEGED_INTENTS=0/1
- Tips confirm with a compact public tier-emoji line instead of reactions; errors and usage respond ephemerally
- Reaction-based pagination replaced with button components
- Wallet↔user lookup commands (wfu/ufw) are now admin-only
- Python 3.14, discord.py 2.7, tortoise-orm 1.1, redis-py 8 (replacing abandoned aioredis/aioredis-lock), exact dependency pins
- Docker image on python:3.14-slim running as a non-root user; CI actions pinned and tests run on pull requests
- Removed: tip_legacy cog, dead burn command, prefix configuration (flag still accepted but unused)

## [4.0.1] - 2019-12-04

- Fix ordering of stats commands for postgres (SQLite still doesn't order correctly due to tortoise/tortoise-orm#256)
- Add !legacyboard which is all-time top tippers
- Make !ballers reset every year
- Use rapidjson
- Misc bug fixes

## [4.0.0] - 2019-12-02

- Initial Release