from railway_sdk import define_railway, github, group, postgres, preserve, project, redis, service


@define_railway
def main(ctx=None):
    repo = github("johngthecreator/betbetbet", branch="main")

    # Use the dedicated database helpers (not bare `service(...)`) so Railway
    # provisions the actual managed Postgres/Redis image/config, rather than an
    # empty service shell — bare `service("Postgres")` is what stripped these
    # down to nothing last time.
    db = postgres("Postgres")
    cache = redis("Redis")

    # The SDK's ref objects (db.env["X"]) only support a single reference per
    # env var — no composing multiple refs into one string. Railway's classic
    # ${{Service.VAR}} template syntax still works as a plain literal string
    # though (resolved server-side), so build the +psycopg-prefixed URL that
    # way instead of trying to do it client-side in Python.
    shared_env = {
        "DISCORD_TOKEN": preserve(),
        "GOOGLE_API_KEY": preserve(),
        "BRIGHTDATA_API_KEY": preserve(),
        # psycopg_pool wants the plain libpq-style URL Postgres hands out
        "CP_URL": db.env["DATABASE_URL"],
        # SQLAlchemy's create_engine needs the +psycopg dialect prefix, or it
        # defaults to looking for psycopg2 (not installed)
        "DB_URL": "postgresql+psycopg://${{Postgres.PGUSER}}:${{Postgres.PGPASSWORD}}@${{Postgres.PGHOST}}:${{Postgres.PGPORT}}/${{Postgres.PGDATABASE}}",
        # bot needs this too — it publishes tasks via agent_call.delay(), which
        # goes through the same Celery app/broker tasks.py defines. Without it,
        # tasks.py falls back to redis://localhost:6379, which doesn't exist in
        # the bot's container, so dispatched tasks silently never reach worker.
        "REDIS_URL": cache.env["REDIS_URL"],
    }

    # `limits=` isn't a real field (silently dropped) — the actual schema key
    # is deploy.limitOverride.containers.{cpu, memoryBytes}.
    bot = service(
        "bot",
        source=repo,
        start="uv run python main.py",
        env=shared_env,
        deploy={"limitOverride": {"containers": {"cpu": 1, "memoryBytes": 1024 * 1024 * 1024}}},
    )

    worker = service(
        "worker",
        source=repo,
        start="uv run celery -A tasks worker --pool=threads --concurrency=10 --loglevel=info",
        env=shared_env,
        deploy={"limitOverride": {"containers": {"cpu": 1, "memoryBytes": 1024 * 1024 * 1024}}},
    )

    return project("betbetbet", resources=[group("app", [db, cache, bot, worker])])
