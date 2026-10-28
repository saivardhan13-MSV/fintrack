from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

CENT = Decimal("0.01")


def to_cents(amount: Decimal | str | int) -> int:
    """Convert a decimal currency amount to integer cents, rounding half-up."""
    return int(Decimal(str(amount)).quantize(CENT, rounding=ROUND_HALF_UP) * 100)


def from_cents(cents: int) -> Decimal:
    return (Decimal(cents) / 100).quantize(CENT)


def parse_amount(raw: str) -> Decimal:
    """Parse bank-statement amounts such as '-12.50', '$1,204.00' or '(45.10)'."""
    text = raw.strip().replace("$", "").replace(",", "").replace(" ", "")
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1]
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError(f"invalid amount '{raw}'") from None
    if not value.is_finite():
        raise ValueError(f"invalid amount '{raw}'")
    return -value if negative else value
