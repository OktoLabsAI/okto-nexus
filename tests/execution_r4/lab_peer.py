"""Scriptable causal peer for R4 unit-contract campaigns.

This is a synthetic peer, never a provider or multi-host qualification.
It can lose a reply after a durable commit while preserving the canonical
receipt for a query and refusing a changed intent under the same ID.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LabReceipt:
    operation_id: str
    intent_hash: str
    stage: str
    possible_effect: bool
    retry_safe: bool


class CausalPeer:
    def __init__(self) -> None:
        self._receipts: dict[str, LabReceipt] = {}
        self.effect_count = 0
        self.drop_next_reply = False

    def submit(self, operation_id: str, intent_hash: str) -> LabReceipt | None:
        old = self._receipts.get(operation_id)
        if old is not None:
            if old.intent_hash != intent_hash:
                raise ValueError("same operation_id with different intent")
            return old
        receipt = LabReceipt(operation_id, intent_hash, "SUCCEEDED", True, False)
        self._receipts[operation_id] = receipt
        self.effect_count += 1
        if self.drop_next_reply:
            self.drop_next_reply = False
            return None
        return receipt

    def query(self, operation_id: str) -> LabReceipt | None:
        return self._receipts.get(operation_id)
