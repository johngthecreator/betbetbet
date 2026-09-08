import os
import sqlite3

from langchain_core.messages import BaseMessage, ToolMessage, ToolCall
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.tools import tool
from langgraph.func import task, entrypoint
from langgraph.checkpoint.postgres import PostgresSaver

from sqlmodel import Session, select
from psycopg_pool import ConnectionPool

from utils import brightdata_scraper
from models import Sale
from db import engine
from parsers import parse_nike_product_detail, parse_gymshark_product_detail, parse_patagonia_product_detail, parse_urbanoutfitters_product_detail
from prompts import GET_PRODUCT_DETAIL_FORMAT, GRAB_SALES_FORMAT
from schemas import BrandEnum

from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("GOOGLE_API_KEY")
CP_URL = os.getenv("CP_URL")


pool = ConnectionPool(CP_URL, min_size=1, max_size=10, kwargs={"autocommit": True})
memory = PostgresSaver(pool)
memory.setup()


@tool
def get_product_detail(target_url: str, brand: BrandEnum):
    """Search target url and use the correct brand parser.

    Args:
        target_url: url of the page we're grabbing 
        brand: brand that determines which parser we're using
    """

    response = brightdata_scraper(target_url)

    match brand:
        case BrandEnum.nike:
            return parse_nike_product_detail(response.text)
        case BrandEnum.patagonia:
            return parse_patagonia_product_detail(response.text)
        case BrandEnum.urban_outfitters:
            return parse_urbanoutfitters_product_detail(response.text)
        case BrandEnum.gymshark:
            return parse_gymshark_product_detail(response.text)

@tool
def grab_sales(brand: BrandEnum, department: str | None):
    """grabs the most recently scraped sales from the database, filtering by brand and department.

    Args:
        brand: brand that determines which parser we're using
        department: the department that the clothes are from. (men, women, kids, etc)
    """

    with Session(engine) as session:
        statement = select(Sale).where(Sale.source == brand)
        if department != None:
            statement = select(Sale.name, Sale.current_price, Sale.url).where(Sale.source == brand).where(Sale.department == department)

        return session.exec(statement).all()


tools = [get_product_detail, grab_sales]

llm = ChatGoogleGenerativeAI(
    model="gemini-3.5-flash-lite",
    temperature=0.1,
    max_retries=2,
    google_api_key=api_key,
)

llm_with_tools = llm.bind_tools(tools)
tools_by_name = {t.name: t for t in tools}

@task
def call_llm(messages: list[BaseMessage]):
  return llm_with_tools.invoke(messages)

@task
def call_tool(tool_call: ToolCall) -> ToolMessage:
    tool_fn = tools_by_name[tool_call["name"]]
    result = tool_fn.invoke(tool_call["args"])
    content = str(result)
    if tool_call["name"] == "grab_sales":
      content = f"{GRAB_SALES_FORMAT}{result}"
    if tool_call["name"] == "get_product_detail":
      content = f"{GET_PRODUCT_DETAIL_FORMAT}{result}"
    return ToolMessage(content=content, name=tool_call["name"], tool_call_id=tool_call["id"])

@entrypoint(checkpointer=memory)
def shop_bot(messages: list[BaseMessage], *, previous: list[BaseMessage] | None = None):
    previous = previous or []
    messages = previous + messages

    response = call_llm(messages).result()

    while response.tool_calls:
        tool_results = [call_tool(tc).result() for tc in response.tool_calls]
        messages = messages + [response, *tool_results]
        response = call_llm(messages).result()
        messages = messages + [response]

    return entrypoint.final(value=response, save=messages + [response])
