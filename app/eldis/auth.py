from dataclasses import dataclass


@dataclass
class Auth:
    username: str
    password: str
    key: str
