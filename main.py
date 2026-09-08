import os
import asyncio
from dotenv import load_dotenv
from parsers import (
    parse_gymshark_products,
    parse_nike_products,
    parse_patagonia_products,
    parse_urbanoutfitters_products,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from utils import brightdata_scraper
from sqlmodel import Session, update
from dataclasses import asdict

from models import Sale
from db import DB_URL, engine
from discord_bot import bot

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

scheduler = AsyncIOScheduler(
  jobstores={"default": SQLAlchemyJobStore(url=DB_URL)}
)

def check_discounts():
    sellers = [
            {"url": "https://www.urbanoutfitters.com/mens-clothing-sale", "parser": parse_urbanoutfitters_products, "department": "men", "source":"urban_outfitters"},
            {"url": "https://www.urbanoutfitters.com/womens-clothing-sale", "parser": parse_urbanoutfitters_products, "department": "women", "source":"urban_outfitters"},
            {"url": "https://www.nike.com/w/mens-sale-3yaepznik1", "parser": parse_nike_products, "department": "men", "source":"nike"},
            {"url": "https://www.nike.com/w/womens-sale-3yaepz5e1x6", "parser": parse_nike_products, "department": "women", "source":"nike"},
            {"url": "https://www.gymshark.com/collections/last-chance/mens", "parser": parse_gymshark_products, "department": "men", "source":"gymshark"},
            {"url": "https://www.gymshark.com/collections/last-chance/womens", "parser": parse_gymshark_products, "department": "women", "source":"gymshark"},
            {"url": "https://www.patagonia.com/shop/web-specials/mens", "parser": parse_patagonia_products, "department": "men", "source":"patagonia"},
            {"url": "https://www.patagonia.com/shop/web-specials/womens", "parser": parse_patagonia_products, "department": "women", "source":"patagonia"},
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
    scheduler.add_job(check_discounts, "cron", day_of_week="mon", hour=23, minute=0)
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
