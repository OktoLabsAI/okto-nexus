"""Admission accounting for the proposed SI-038 Codex campaign.

The driver reserves before an effect can occur, including automatic dispatch
of the accepted queue entry. It supplies token deltas and terminal facts only
after matching the exact operation, thread and turn in the journal. This module
neither starts a campaign nor handles credentials.
"""

import json
import os
from pathlib import Path
from threading import Lock


STEPS = ('setup', 'home', 'interactive', 'queued', 'steer')
GROUPS = {step: 'interactive' if step == 'steer' else step for step in STEPS}
PROVISION = 75_000
PREVENTIVE = 450_000
OBSERVED_LIMIT = 500_000


class BudgetStop(RuntimeError):
    """Close new admissions and retain the records for reconciliation."""


class CampaignBudget:
    """One writer per campaign directory, with permanent recorded provisions."""

    def __init__(self, root: Path):
        self.path = root / 'si038-budget.jsonl'
        self._lock = Lock()
        self._reservations = {}
        self._observed = {}
        self._terminal = set()
        self._stopped = False
        try:
            self._publish('x', dict(event='opened', steps=STEPS, provision=PROVISION,
                                    preventive=PREVENTIVE, observed_limit=OBSERVED_LIMIT))
        except FileExistsError as error:
            # An interrupted run may have reached an effect. Recovery reads its
            # original receipts separately. It never starts another budget here.
            raise BudgetStop('CAMPAIGN_ALREADY_STARTED') from error

    def _publish(self, mode, record):
        with self.path.open(mode, encoding='utf-8', newline='\n') as stream:
            stream.write(json.dumps(record, separators=(',', ':')) + '\n')
            stream.flush()
            os.fsync(stream.fileno())

    def _record(self, record):
        try:
            self._publish('a', record)
        except OSError as error:
            self._stopped = True
            raise BudgetStop('BUDGET_RECORD_NOT_DURABLE') from error

    def _stop(self, reason):
        self._stopped = True
        self._record(dict(event='stopped', reason=reason))
        raise BudgetStop(reason)

    def _charge(self, extra=None):
        provisions = {}
        steps = list(self._reservations)
        if extra is not None:
            steps.append(extra)
        for step in steps:
            group = GROUPS[step]
            provisions[group] = provisions.get(group, 0) + PROVISION
        return sum(max(provision, self._observed.get(group, 0)) for group, provision in provisions.items())

    def reserve(self, step: str, intent_id: str) -> None:
        """Durably claim one admission before the caller requests an effect."""
        with self._lock:
            if self._stopped:
                raise BudgetStop('CAMPAIGN_STOPPED')
            index = len(self._reservations)
            if index == len(STEPS) or step != STEPS[index]:
                self._stop('ADMISSION_ORDER_CHANGED')
            if (not isinstance(intent_id, str) or not intent_id.isprintable()
                    or not 1 <= len(intent_id) <= 160 or intent_id in self._reservations.values()):
                self._stop('INTENT_INVALID_OR_ALREADY_RESERVED')
            if step in ('home', 'interactive') and STEPS[index - 1] not in self._terminal:
                self._stop('PREVIOUS_ACCOUNTING_UNCONFIRMED')
            if step in ('queued', 'steer') and 'interactive' in self._terminal:
                self._stop('INTERACTIVE_TURN_ALREADY_FINISHED')
            if step == 'steer' and 'queued' in self._observed:
                self._stop('QUEUED_TURN_ALREADY_STARTED')
            charged = self._charge(extra=step)
            if charged >= PREVENTIVE:
                self._stop('PREVENTIVE_BUDGET_REACHED')
            self._record(dict(event='reserved', step=step, intent_id=intent_id, group=GROUPS[step],
                              provision=PROVISION, charged=charged))
            self._reservations[step] = intent_id

    def observe(self, group: str, tokens: int, *, terminal: bool = False) -> None:
        """Record an exact group's observed delta, including late observations.

        The active native turn and its reorientation share one group. Their two
        permanent provisions are compared with that group's single delta.
        A terminal execution and observed delta are lower bounds for billing.
        """
        with self._lock:
            if group not in {GROUPS[step] for step in self._reservations}:
                self._stop('NO_RESERVATION_FOR_USAGE')
            if type(tokens) is not int or tokens < self._observed.get(group, 0):
                self._stop('USAGE_COUNTER_UNKNOWN_OR_REGRESSED')
            if type(terminal) is not bool:
                self._stop('TERMINAL_FACT_UNKNOWN')
            self._observed[group] = tokens
            if terminal:
                self._terminal.add(group)
            observed = sum(self._observed.values())
            charged = self._charge()
            self._record(dict(event='observed', group=group, group_tokens=tokens, observed=observed,
                              charged=charged, terminal=group in self._terminal, final_billing=False))
            if self._stopped:
                raise BudgetStop('CAMPAIGN_STOPPED')
            if observed >= OBSERVED_LIMIT:
                self._stop('OBSERVED_BUDGET_STOP')
            if charged >= PREVENTIVE:
                self._stop('PREVENTIVE_BUDGET_REACHED')

    def stop_uncertain(self) -> None:
        """Keep all provisions when a request, receipt or usage is uncertain."""
        with self._lock:
            if self._stopped:
                raise BudgetStop('CAMPAIGN_STOPPED')
            self._stop('EFFECT_OR_USAGE_UNCERTAIN')
