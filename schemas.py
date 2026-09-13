from enum import Enum

from pydantic import BaseModel


class BrandEnum(str, Enum):
    nike = "nike"
    patagonia = "patagonia"
    gymshark = "gymshark"
    urban_outfitters = "urban_outfitters"
    allsaints = "allsaints"


class UserQuery(BaseModel):
    user_id: str
    query: str
