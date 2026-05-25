from app.eldis.client import get_client


def get_devices(object_id: int):
    client = get_client()
    client._login()
    return client.get_devices()
