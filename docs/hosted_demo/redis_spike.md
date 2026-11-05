# Redis checkpointer spike (2026-11-04)

Stopped at question 1. Questions 2–6 were not run. No custom saver was written.

## 1. Does a Redis saver work with the installed LangGraph?

Package: `langgraph-checkpoint-redis` 0.6.0 (`RedisSaver` in `langgraph.checkpoint.redis`). It requires `langgraph-checkpoint>=4.1.1,<5`. Both LangGraph versions under test resolve `langgraph-checkpoint` 4.3.1.

Imported and called `RedisSaver.setup()` on:

- LangGraph 1.2.9 (the version installed in this repo) with checkpoint-redis 0.6.0
- LangGraph 1.2.14 (the #345 bump) with checkpoint-redis 0.6.0, in a separate `uv run --with` environment

Both calls raised `RedisSearchError: Error while fetching checkpoint index info: unknown command 'FT.INFO'`.

Redis server: Homebrew `redis-server` 8.10.2, started as

`redis-server --port 6380 --bind 127.0.0.1 --save "" --appendonly no --daemonize yes`

`MODULE LIST` returned only `vectorset`. `JSON.SET` and `FT.CREATE` / `FT.INFO` are unknown commands. The package's own README says RedisJSON and RediSearch are required (included in Redis Stack, or in Redis 8.0+ when those modules are built in). This Homebrew build does not have them.

Docker was the other local option (`redis/redis-stack-server`). `open -a Docker` did not bring up a daemon: after 60 seconds there was no socket at `~/.docker/run/docker.sock`.

The saver exists and imports on both LangGraph versions. It does not run against the Redis that is installed here.

Not run, read from the installed 0.6.0 source only: `BaseRedisSaver` constructs `JsonPlusRedisSerializer()` itself and `RedisSaver` does not take a `serde=` argument, so the project's msgpack allowlist cannot be passed in. That is question 2, and it was not tested with a checkpoint.

## 2–6

Not run. Setup never returned a saver that could store a checkpoint.

## Options

- Rerun this spike against Redis Stack (`redis/redis-stack-server` or another build that answers `FT.INFO` and `JSON.SET`). Same package, 0.6.0. No older release was installed.
- Postgres (`langgraph-checkpoint-postgres`) was not tested.
- A custom saver needs Vu's approval. None was written.
