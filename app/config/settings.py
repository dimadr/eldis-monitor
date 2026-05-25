import os
from dotenv import load_dotenv

load_dotenv()

ELDIS_API_URL = os.getenv("ELDIS_API_URL", "https://api.eldis24.ru")
ELDIS_LOGIN = os.getenv("ELDIS_LOGIN", "")
ELDIS_PASSWORD = os.getenv("ELDIS_PASSWORD", "")
ELDIS_API_KEY = os.getenv("ELDIS_API_KEY", "")

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///eldis.db")

ALERT_EMAIL_FROM = os.getenv("ALERT_EMAIL_FROM", "")
ALERT_EMAIL_TO = os.getenv("ALERT_EMAIL_TO", "")
ALERT_SMTP_HOST = os.getenv("ALERT_SMTP_HOST", "")
ALERT_SMTP_PORT = int(os.getenv("ALERT_SMTP_PORT", "465"))
ALERT_SMTP_USER = os.getenv("ALERT_SMTP_USER", "")
ALERT_SMTP_PASSWORD = os.getenv("ALERT_SMTP_PASSWORD", "")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

ANOMALY_THRESHOLD = 10  # Порог аномалии (зависит от типа данных - для тепла Гкал/сут примерно 5-10)
NO_DATA_MINUTES = 10

# Режим работы
MOCK_MODE = os.getenv("MOCK_MODE", "false").lower() == "true"
