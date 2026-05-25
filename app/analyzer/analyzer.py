from app.config import settings
from app.models import Reading


def analyze(prev: Reading | None, current: Reading | None) -> str:
    if current is None:
        return "NO_DATA"

    if prev is None:
        return "ok"

    if current.value < prev.value:
        return "COUNTER_RESET"

    delta = current.value - prev.value
    if delta > settings.ANOMALY_THRESHOLD:
        return "ANOMALY"

    return "ok"
