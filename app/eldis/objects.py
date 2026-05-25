from app.eldis.client import get_client


def get_devices():
    """Получить список устройств (точек учета)
    
    Returns:
        Данные об устройствах или None в случае ошибки
    """
    client = get_client()
    # _login вызывается автоматически в get(), если не mock режим
    return client.get_devices()
