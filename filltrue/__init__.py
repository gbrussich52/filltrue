"""FillTrue — an options agent that only believes fills."""

from filltrue.ledger import Ledger, is_true_fill
from filltrue.policy import decide_exit, gate_entry, profit_frac

__version__ = "0.1.0"
__all__ = [
    "Ledger",
    "decide_exit",
    "gate_entry",
    "is_true_fill",
    "profit_frac",
]
