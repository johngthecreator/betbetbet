from railway_sdk import define_railway, github, group, preserve, project, service


@define_railway
def main(ctx=None):
    repo = github("johngthecreator/betbetbet", branch="main")

    # Adopt the Postgres/Redis plugins already provisioned in the project —
    # no `source`, so IaC manages settings/vars without trying to recreate them.
    db = service("Postgres")
    cache = service("Redis")

    shared_env = {
        "DISCORD_TOKEN": preserve(),
        "GOOGLE_API_KEY": preserve(),
        "BRIGHTDATA_API_KEY": preserve(),
        "DB_URL": db.env["DATABASE_URL"],
        "CP_URL": db.env["DATABASE_URL"],
    }

    bot = service(
        "bot",
        source=repo,
        start="uv run python main.py",
        env=shared_env,
        limits={"cpu": 0.5, "memory_bytes": 512 * 1024 * 1024},
    )

    worker = service(
        "worker",
        source=repo,
        start="uv run celery -A tasks worker --pool=threads --concurrency=10 --loglevel=info",
        env={**shared_env, "REDIS_URL": cache.env["REDIS_URL"]},
        limits={"cpu": 1, "memory_bytes": 512 * 1024 * 1024},
    )

    return project("betbetbet", resources=[group("app", [db, cache, bot, worker])])
