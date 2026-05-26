from pydantic import SecretStr

REDACTED_SECRET = "********"
FORBIDDEN_EXCHANGE_ACTIONS = frozenset(
    {
        "place_trade",
        "place_order",
        "cancel_order",
        "change_leverage",
        "transfer_funds",
        "withdraw_funds",
    }
)


class ForbiddenExchangeActionError(RuntimeError):
    """Raised if code attempts to add a non-read-only exchange action."""


def redact_secret(value: str | SecretStr | None) -> str | None:
    if value is None:
        return None
    return REDACTED_SECRET


def assert_read_only_action(action: str) -> None:
    if action in FORBIDDEN_EXCHANGE_ACTIONS:
        raise ForbiddenExchangeActionError(f"Exchange action is not allowed: {action}")

