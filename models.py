from datetime import datetime

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

class Sale(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    source: str
    name: str
    url: str
    scraped_at: datetime
    image_url: str | None
    current_price: float
    original_price: float | None
    discount_percent: float | None
    rating: float | None
    badges: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    colors: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    department: str
    is_active: bool = True
