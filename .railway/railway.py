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

    # The SDK only supports a plain literal string or a single reference per
    # env var — no composing multiple refs into one string. DB_URL and CP_URL
    # both just point at the raw Postgres.DATABASE_URL; the +psycopg dialect
    # rewrite SQLAlchemy needs happens in db.py instead.
    shared_env = {
        "DISCORD_TOKEN": preserve(),
        "GOOGLE_API_KEY": preserve(),
        "BRIGHTDATA_API_KEY": preserve(),
        "CP_URL": db.env["DATABASE_URL"],
        "DB_URL": db.env["DATABASE_URL"],
    }

    # `limits=` isn't a real field (silently dropped) — the actual schema key
    # is deploy.limitOverride.containers.{cpu, memoryBytes}.
    bot = service(
        "bot",
        source=repo,
        start="uv run python main.py",
        env=shared_env,
        deploy={"limitOverride": {"containers": {"cpu": 0.5, "memoryBytes": 512 * 1024 * 1024}}},
    )

    worker = service(
        "worker",
        source=repo,
        start="uv run celery -A tasks worker --pool=threads --concurrency=10 --loglevel=info",
        env={**shared_env, "REDIS_URL": cache.env["REDIS_URL"]},
        deploy={"limitOverride": {"containers": {"cpu": 1, "memoryBytes": 512 * 1024 * 1024}}},
    )

    return project("betbetbet", resources=[group("app", [db, cache, bot, worker])])
