"""OCC option-symbol parsing and construction.

OCC format (Alpaca's, no spaces): ``<ROOT><YYMMDD><C|P><STRIKE*1000, 8 digits>``
e.g. ``SPY240329C00500000`` -> SPY, 2024-03-29, call, strike 500.0.

The root is variable-length, so everything is parsed right-anchored: the last
8 chars are the strike, the char before that is the type, the 6 before that are
the date, and whatever remains on the left is the underlying root.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

_TYPE = {"C": "call", "P": "put"}
_TYPE_INV = {"call": "C", "put": "P"}
# root(>=1) + YYMMDD(6) + C/P(1) + strike(8)
_OCC_RE = re.compile(r"^(?P<root>[A-Z0-9]{1,6}?)(?P<ymd>\d{6})(?P<cp>[CP])(?P<strike>\d{8})$")


@dataclass(frozen=True)
class Contract:
    underlying: str
    expiry: date
    opt_type: str  # 'call' | 'put'
    strike: float
    symbol: str


def parse_occ(symbol: str) -> Contract:
    """Parse an OCC option symbol into a Contract, or raise ValueError."""
    s = symbol.strip().upper()
    m = _OCC_RE.match(s)
    if not m:
        raise ValueError(f"not a valid OCC option symbol: {symbol!r}")
    ymd = m.group("ymd")
    try:
        expiry = date(2000 + int(ymd[:2]), int(ymd[2:4]), int(ymd[4:6]))
    except ValueError as e:
        raise ValueError(f"bad expiry in {symbol!r}: {e}") from e
    return Contract(
        underlying=m.group("root"),
        expiry=expiry,
        opt_type=_TYPE[m.group("cp")],
        strike=int(m.group("strike")) / 1000.0,
        symbol=s,
    )


def build_occ(underlying: str, expiry: date, opt_type: str, strike: float) -> str:
    """Build an OCC option symbol. Inverse of parse_occ."""
    cp = _TYPE_INV.get(opt_type.lower()) or (
        "C" if opt_type.upper().startswith("C") else "P"
    )
    strike_int = int(round(strike * 1000))
    if strike_int < 0 or strike_int > 99_999_999:
        raise ValueError(f"strike out of range for OCC encoding: {strike}")
    return f"{underlying.upper()}{expiry:%y%m%d}{cp}{strike_int:08d}"
