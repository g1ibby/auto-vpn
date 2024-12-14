from dataclasses import dataclass
from typing import List, Optional
from decimal import Decimal

@dataclass
class Region:
    id: str
    city: Optional[str]
    country: str
    country_code: str
    provider: str

@dataclass
class InstanceType:
    id: str
    vcpus: int
    memory: int  # in MB
    disk: int    # in GB
    transfer: Optional[int]  # in TB
    price_monthly: Decimal
    provider: str
