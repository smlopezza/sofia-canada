from zoneinfo import ZoneInfo
from datetime import datetime

# Map common Canadian city names to the appropriate IANA timezone string.
# Used to determine local time for users and messages.
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
    """Return the IANA timezone for a given city name.

    If the city does not exist in the lookup map, default to Toronto/Eastern time.
    """
    return CITY_TIMEZONE_MAP.get(city.lower().strip(), "America/Toronto")


def local_now(timezone: str) -> datetime:
    """Return the current local datetime for a given timezone."""
    return datetime.now(ZoneInfo(timezone))


def local_hour(timezone: str) -> int:
    """Return the current hour (0-23) in the specified timezone."""
    return local_now(timezone).hour


def is_sendable(timezone: str) -> bool:
    """Determine whether it is an acceptable local hour to send messages.

    Returns True if the local hour is between 7:00 and 20:59.
    """
    hour = local_hour(timezone)
    return 7 <= hour < 21
