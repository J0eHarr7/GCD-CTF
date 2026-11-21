"""
legacy_arithmetic.py

Simulates a legacy fixed-width billing engine that Lina's Blog inherited
from an older invoicing system during a platform migration. The original
system ran on 32-bit signed integer registers, so all monetary arithmetic
here is deliberately emulated at that width rather than using Python's
arbitrary-precision integers.

NOTE FOR MAINTAINERS (flavor text — not actually true, this is the bug):
  We keep this module around purely for backwards-compatible invoice
  numbering with the old ledger exports. It should behave identically
  to normal arithmetic for any "reasonable" order.
"""

INT32_MIN = -2147483648
INT32_MAX = 2147483647
_MODULUS = 1 << 32  # 2**32


def to_int32(value: int) -> int:
    """Truncate an arbitrary Python int down to a 32-bit signed register,
    wrapping around on overflow exactly as a fixed-width C/COBOL style
    accumulator would.
    """
    value &= _MODULUS - 1  # keep low 32 bits
    if value >= (_MODULUS >> 1):  # >= 2**31 -> negative in two's complement
        value -= _MODULUS
    return value


def legacy_mul(a: int, b: int) -> int:
    """Multiply two values using the fixed-width accumulator."""
    return to_int32(a * b)


def legacy_add(a: int, b: int) -> int:
    """Add two values using the fixed-width accumulator."""
    return to_int32(a + b)


def compute_line_total(unit_price_cents: int, quantity: int) -> int:
    """Compute a line-item total the way the legacy billing component does.

    unit_price_cents and quantity are both plain Python ints coming from
    (mostly) trusted sources, but the *arithmetic itself* is the bug:
    for large enough quantities, unit_price_cents * quantity exceeds the
    32-bit signed range and silently wraps, potentially producing a very
    small or even negative total for an extremely expensive purchase.
    """
    return legacy_mul(unit_price_cents, quantity)
