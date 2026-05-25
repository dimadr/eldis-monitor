from dataclasses import dataclass
from datetime import datetime


@dataclass
class Reading:
    device_id: int
    timestamp: datetime
    value: float
    status: str = "ok"
