import re

# Card-processor noise that banks prepend to the merchant name.
_PREFIX = re.compile(
    r"^(POS|ACH|DEBIT|CREDIT|PURCHASE|RECURRING|CHECKCARD|SQ\s*\*|TST\s*\*|PAYPAL\s*\*)\s*",
    re.IGNORECASE,
)


def normalize_merchant(text: str) -> str:
    """Reduce a raw statement line to a stable merchant key.

    'POS NETFLIX.COM 866-579-7172' -> 'NETFLIX.COM'
    'SPOTIFY USA*P2A9F1'           -> 'SPOTIFY USA'
    'PAYPAL *HULU 402-935-7733'    -> 'HULU'
    """
    s = text.strip().upper()
    while (stripped := _PREFIX.sub("", s)) != s:
        s = stripped
    s = s.split("*")[0]
    # Tokens containing digits are usually reference numbers, phone numbers or store ids.
    tokens = [t for t in s.split() if not any(ch.isdigit() for ch in t)]
    result = " ".join(tokens).strip(" -.,#")
    return (result or text.strip().upper())[:128]
