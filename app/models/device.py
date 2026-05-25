from dataclasses import dataclass


@dataclass
class Device:
    id: int
    object_id: int
    name: str
    type: str
