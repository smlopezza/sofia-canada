from zoneinfo import ZoneInfo
from datetime import datetime

CITY_TIMEZONE_MAP = {
    # Ontario / Quebec / Eastern
    "toronto": "America/Toronto", "ottawa": "America/Toronto",
    "montreal": "America/Toronto", "hamilton": "America/Toronto",
    "mississauga": "America/Toronto", "brampton": "America/Toronto",
    "london": "America/Toronto", "kitchener": "America/Toronto",
    "windsor": "America/Toronto", "kingston": "America/Toronto",
    "quebec city": "America/Toronto",
    # BC / Pacific
    "vancouver": "America/Vancouver", "surrey": "America/Vancouver",
    "burnaby": "America/Vancouver", "victoria": "America/Vancouver",
    "richmond": "America/Vancouver", "kelowna": "America/Vancouver",
    # Alberta / Mountain
    "calgary": "America/Edmonton", "edmonton": "America/Edmonton",
    "red deer": "America/Edmonton", "lethbridge": "America/Edmonton",
    # Manitoba / Central
    "winnipeg": "America/Winnipeg", "brandon": "America/Winnipeg",
    # Saskatchewan (no DST)
    "saskatoon": "America/Regina", "regina": "America/Regina",
    # Atlantic
    "halifax": "America/Halifax", "moncton": "America/Halifax",
    "fredericton": "America/Halifax", "saint john": "America/Halifax",
    "charlottetown": "America/Halifax",
    # Newfoundland
    "st. john's": "America/St_Johns", "st johns": "America/St_Johns",
}


def get_timezone(city: str) -> str:
    return CITY_TIMEZONE_MAP.get(city.lower().strip(), "America/Toronto")


def local_now(timezone: str) -> datetime:
    return datetime.now(ZoneInfo(timezone))


def local_hour(timezone: str) -> int:
    return local_now(timezone).hour


def is_sendable(timezone: str) -> bool:
    """Returns True if current local time is between 6am and 9pm."""
    hour = local_hour(timezone)
    return 6 <= hour < 21
