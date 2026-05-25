from datetime import datetime as dt
from app.eldis.client import get_client


def get_current_reading(device_id: int):
    client = get_client()
    return client.get_normalized_readings(str(device_id))
