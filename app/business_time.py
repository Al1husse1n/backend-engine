"""Business calendar for Meri. Implicit dates follow Ethiopia, not the server clock."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

BUSINESS_ZONE = ZoneInfo("Africa/Addis_Ababa")


def business_now() -> datetime:
    return datetime.now(BUSINESS_ZONE)


def business_today() -> date:
    return business_now().date()
