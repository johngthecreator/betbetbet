import os
import asyncio
from dotenv import load_dotenv
from parsers import parse_urbanoutfitters_products
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from utils import brightdata_scraper
from sqlmodel import Session, update
from dataclasses import asdict

from models import Sale
from db import engine
from discord_bot import bot

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
DB_URL = os.getenv("DB_URL")

scheduler = AsyncIOScheduler(
  jobstores={"default": SQLAlchemyJobStore(url=DB_URL)}
)

def check_discounts():
    sellers = [
            {"url": "https://www.urbanoutfitters.com/mens-clothing-sale", "parser": parse_urbanoutfitters_products, "department": "men", "source":"urban_outfitters"},
            {"url": "https://www.urbanoutfitters.com/womens-clothing-sale", "parser": parse_urbanoutfitters_products, "department": "women", "source":"urban_outfitters"}
            ]
    for seller in sellers:
        response = brightdata_scraper(seller["url"])
        parsed_products = seller["parser"](response.text)
        with Session(engine) as session:
            session.exec(
                    update(Sale)
                    .where(Sale.source == seller["source"])
                    .where(Sale.department == seller["department"])
                    .values(is_active=False)
                    )
            for pp in parsed_products:
                session.add(Sale(**asdict(pp), department=seller["department"]))
                print(pp.name)
            session.commit()

async def main():
    scheduler.add_job(check_discounts, "cron", day_of_week="sun", hour=23, minute=0)
    # scheduler.add_job(check_discounts, "interval", minutes=5)
    scheduler.start()
    try:
        async with bot:
            await bot.start(str(DISCORD_TOKEN))
    finally:
        scheduler.shutdown()

try:
    asyncio.run(main())
except KeyboardInterrupt:
    pass
