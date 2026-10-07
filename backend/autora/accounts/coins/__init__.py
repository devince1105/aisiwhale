"""Whale Coins: the ledger core (P3-A, D-223).

Coins are given by the platform and spent on it — never sold, moved between readers or cashed.
This package keeps the accounts and answers six questions: grant, spend, refund, adjust,
balance, reconcile. It knows nothing of tiers, months, sign-ins or addresses: who gets how many,
and when, is the grant policy's (P3-B); what a coin buys is each feature's (P4 onwards).
"""

from autora.accounts.coins.grants import grant_monthly
from autora.accounts.coins.ledger import (
    CapExceeded,
    CoinError,
    IdempotencyConflict,
    InsufficientCoins,
    NotRefundable,
    Posted,
    adjust,
    balance,
    grant,
    refund,
    spend,
)
from autora.accounts.coins.models import (
    CoinAccount,
    CoinEntry,
    CoinTxn,
    CoinWallet,
    OwnerType,
    SystemAccount,
    TxnKind,
)
from autora.accounts.coins.reconcile import Reconciliation, reconcile

__all__ = [
    "CapExceeded",
    "CoinAccount",
    "CoinEntry",
    "CoinError",
    "CoinTxn",
    "CoinWallet",
    "IdempotencyConflict",
    "InsufficientCoins",
    "NotRefundable",
    "OwnerType",
    "Posted",
    "Reconciliation",
    "SystemAccount",
    "TxnKind",
    "adjust",
    "balance",
    "grant",
    "grant_monthly",
    "reconcile",
    "refund",
    "spend",
]
