from dataclasses import dataclass
from decimal import Decimal


@dataclass
class Region:
    id: str
    city: str | None
    country: str
    country_code: str
    provider: str


@dataclass
class InstanceType:
    id: str
    vcpus: int
    memory: int  # in MB
    disk: int  # in GB
    transfer: int | None  # in TB
    price_monthly: Decimal
    provider: str
