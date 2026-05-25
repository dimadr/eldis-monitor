import logging
from app import eldis
from app.storage import get_database
from app.analyzer import analyzer
from app.alerts import email as alerts_email
from app.alerts import telegram as alerts_telegram

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run():
    logger.info("Starting collector...")
    db = get_database()
    db.init_schema()

    devices = eldis.objects.get_devices()
    logger.info(f"Devices response: {devices}")

    # Обработка mock данных
    tv_data = devices.get('response', {}).get('tv', {}).get('listForDevelopment', {})
    if isinstance(tv_data, dict):
        devices_list = list(tv_data.values())
    else:
        devices_list = []

    logger.info(f"Found {len(devices_list)} devices")

    for device_data in devices_list:
        device_id = None
        try:
            device_id = device_data.get("id")
            device_name = device_data.get("name", "")
            object_name = device_data.get("object_name", "")

            logger.info(f"Processing device: {device_name} (ID: {device_id})")

            reading_data = eldis.readings.get_current_reading(device_id)
            if reading_data:
                logger.info(f"Got reading for device {device_id}: {reading_data}")
        except Exception as e:
            logger.error(f"Error processing device {device_id}: {e}")


if __name__ == "__main__":
    run()
