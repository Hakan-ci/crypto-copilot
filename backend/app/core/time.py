from datetime import UTC, datetime


def utc_now() -> datetime:
    return datetime.now(UTC)


def datetime_from_ms(timestamp_ms: int) -> datetime:
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC)

