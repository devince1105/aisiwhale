"""Whale Coins: the ledger core (P3-A, D-223).

Coins are given by the platform and spent on it — never sold, moved between readers or cashed.
This package keeps the accounts and answers six questions: grant, spend, refund, adjust,
balance, reconcile. It knows nothing of tiers, months, sign-ins or addresses: who gets how many,
and when, is the grant policy's (P3-B); what a coin buys is each feature's (P4 onwards).
"""

from autora.accounts.coins.grants import ThisMonth, grant_monthly, this_month
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
    ArticleUnlock,
    CoinAccount,
    CoinEntry,
    CoinTxn,
    CoinWallet,
    OwnerType,
    SystemAccount,
    TxnKind,
)
from autora.accounts.coins.reconcile import Reconciliation, reconcile
from autora.accounts.coins.unlocks import Unlocked, unlock_article, unlock_of, unlocks_of

__all__ = [
    "ArticleUnlock",
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
    "ThisMonth",
    "TxnKind",
    "Unlocked",
    "adjust",
    "balance",
    "grant",
    "grant_monthly",
    "reconcile",
    "refund",
    "spend",
    "this_month",
    "unlock_article",
    "unlock_of",
    "unlocks_of",
]
