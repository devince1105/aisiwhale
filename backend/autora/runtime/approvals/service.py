"""Human approvals (T-206, logs/platform/07_PERMISSION_MODEL.md §4, D-001).

Three ways an approval can be attached:

- **Agent run** (``request_for_run``): a policy decision said ``needs_approval`` in the middle of
  a run. The worker is released, the run stays open in WAITING_APPROVAL and the agent shows
  WAITING{approval}. Approved: the task goes back to READY and the *same* agent resumes the
  *same* run (the task manager only lets that agent claim it). Rejected: the task is cancelled
  (downstream tasks follow through the workflow engine).
- **Human task node** (``request_for_task``): the task itself is the decision (e.g. approve an
  article). Approved: the task SUCCEEDED and the next node unlocks. Rejected: cancelled.
  **Sent back** (``revise``, D-044): the task SUCCEEDED too, with ``decision: revise`` and the
  reason in its output — a workflow loop on that node does the work again (the newsroom's
  draft → review → approve); without one, nothing unlocks differently and it reads as approved,
  so only nodes that loop should be sent back. A reason is required: "change it" says nothing.
- **Standalone** (``request``): a command needing approval (create a project). Whoever issued it
  reacts to APPROVAL_APPROVED / APPROVAL_REJECTED.

Expiry (D-001): an expired approval is marked EXPIRED, but the task keeps waiting; it is not
cancelled. **A task still waiting gets a new approval at once** (D-131): an EXPIRED approval
cannot be decided, so without one the task — and the article behind it — waited for a decision
nobody could make, its workflow RUNNING for days and the operator's count of pending approvals
at zero. The renewal is the reminder: it is asked again, and heard again in the team group.

**Unless someone is asked to decide instead** (D-157, replacing D-156's "silence is consent"):
a domain may say, per action, who decides an approval nobody answered by its expiry
(``delegate_when_unanswered(action, delegate)``: the hook starts that agent's task — the domain
picks whom — and returns its id, or declines). The approval stays PENDING meanwhile, for a
short window more: a person may still decide, and whoever decides first wins (the delegate's
task is cancelled, or its tool told the approval was already decided). The delegate decides
through ``decide_delegated`` — approve or reject, with a reason, recorded as that agent. If it
declines, fails, or does not decide in the window, the approval expires and is asked again
(D-131), and is not delegated again.

Only humans decide — or, past the deadline, the agent a domain named for it.
Automatic approval (policy flag) is a PolicyEngine decision, not an approval.

A domain can act on a decision in the same transaction (T-514): ``on_decided(action, hook)``
registers a hook for approvals of that ``action`` (e.g. ``approve_article`` approves or rejects
the article). It runs before the task moves on; if it raises, the decision is not recorded.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autora.db.models import Approval, ApprovalKind, ApprovalState, Task, TaskState
from autora.runtime.actor import Actor
from autora.runtime.events import catalog as ev
from autora.runtime.events.outbox import emit
from autora.runtime.events.schema import EventPayload, new_event
from autora.runtime.lifecycles import APPROVAL_FSM
from autora.runtime.task_manager import Claim, TaskManager

log = logging.getLogger(__name__)

DEFAULT_EXPIRY = timedelta(hours=24)  # D-001

DecisionOutcome = Literal["approve", "reject", "revise"]
DecisionHook = Callable[
    [AsyncSession, Approval, DecisionOutcome, Actor, str | None], Awaitable[None]
]
DelegateHook = Callable[[AsyncSession, Approval], Awaitable[uuid.UUID | None]]
"""Start the task of whoever decides an approval nobody answered (D-157): its id, or None."""

DELEGATE_WINDOW = timedelta(hours=6)
"""How long the delegate has, before the approval expires and a person is asked again."""

_TASK_DONE = {TaskState.SUCCEEDED, TaskState.FAILED, TaskState.CANCELLED}


class ApprovalError(Exception):
    pass


@dataclass
class ApprovalService:
    task_manager: TaskManager
    default_expiry: timedelta = DEFAULT_EXPIRY
    clock: Callable[[], datetime] = field(default=lambda: datetime.now(UTC))
    hooks: dict[str, DecisionHook] = field(default_factory=dict)
    delegates: dict[str, DelegateHook] = field(default_factory=dict)

    def on_decided(self, action: str, hook: DecisionHook) -> None:
        if action in self.hooks:
            raise ApprovalError(f"a decision hook for {action!r} is already registered")
        self.hooks[action] = hook

    def delegate_when_unanswered(self, action: str, delegate: DelegateHook) -> None:
        """Approvals of ``action`` still pending at their expiry go to ``delegate`` (D-157)."""
        if action in self.delegates:
            raise ApprovalError(f"a delegate for {action!r} is already registered")
        self.delegates[action] = delegate

    # --- requesting ------------------------------------------------------------------------

    async def request_for_run(
        self,
        session: AsyncSession,
        claim: Claim,
        *,
        kind: ApprovalKind | str,
        action: str,
        payload: dict[str, Any],
        summary: str,
        expires_after: timedelta | None = None,
    ) -> Approval:
        approval = await self._create(
            session,
            company_id=claim.task.company_id,
            kind=kind,
            ref_type="agent_run",
            ref_id=claim.run.id,
            task_id=claim.task.id,
            run_id=claim.run.id,
            action=action,
            payload=payload,
            summary=summary,
            requested_by=Actor.agent(claim.agent.id),
            expires_after=expires_after,
        )
        await self.task_manager.suspend_for_approval(session, claim, approval.id)
        return approval

    async def request_for_task(
        self,
        session: AsyncSession,
        task: Task,
        *,
        kind: ApprovalKind | str,
        summary: str,
        payload: dict[str, Any] | None = None,
        action: str | None = None,
        requested_by: Actor | None = None,
        expires_after: timedelta | None = None,
    ) -> Approval:
        if task.state != TaskState.READY:
            raise ApprovalError(f"task {task.id} is {task.state}; only READY tasks can await one")
        approval = await self._create(
            session,
            company_id=task.company_id,
            kind=kind,
            ref_type="task",
            ref_id=task.id,
            task_id=task.id,
            run_id=None,
            action=action,
            payload=payload or {},
            summary=summary,
            requested_by=requested_by or Actor.system("workflow_engine"),
            expires_after=expires_after,
        )
        await self.task_manager.await_approval(session, task, approval.id)
        return approval

    async def request(
        self,
        session: AsyncSession,
        *,
        company_id: uuid.UUID,
        kind: ApprovalKind | str,
        ref_type: str,
        ref_id: uuid.UUID,
        summary: str,
        requested_by: Actor,
        action: str | None = None,
        payload: dict[str, Any] | None = None,
        expires_after: timedelta | None = None,
    ) -> Approval:
        return await self._create(
            session,
            company_id=company_id,
            kind=kind,
            ref_type=ref_type,
            ref_id=ref_id,
            task_id=None,
            run_id=None,
            action=action,
            payload=payload or {},
            summary=summary,
            requested_by=requested_by,
            expires_after=expires_after,
        )

    # --- deciding --------------------------------------------------------------------------

    async def decide(
        self,
        session: AsyncSession,
        approval_id: uuid.UUID,
        *,
        outcome: DecisionOutcome,
        actor: Actor,
        reason: str | None = None,
    ) -> Approval:
        if actor.kind != "human":
            raise ApprovalError("only a human can decide an approval")
        return await self._decide(session, approval_id, outcome=outcome, actor=actor, reason=reason)

    async def decide_delegated(
        self,
        session: AsyncSession,
        approval_id: uuid.UUID,
        *,
        outcome: Literal["approve", "reject"],
        actor: Actor,
        reason: str,
        task_id: uuid.UUID,
    ) -> Approval:
        """The delegate's decision (D-157): only the agent whose task the approval went to, only
        approve or reject, always with a reason. A person who decided first wins: this raises
        ``already ...`` then."""
        if actor.kind != "agent":
            raise ApprovalError("a delegated decision is an agent's")
        if outcome not in ("approve", "reject"):
            raise ApprovalError("a delegate approves or rejects; sending back is a person's")
        if not reason.strip():
            raise ApprovalError("a delegated decision says why")
        approval = await session.get(Approval, approval_id, with_for_update=True)
        if approval is None:
            raise ApprovalError(f"approval {approval_id} not found")
        marker = (approval.payload or {}).get("delegated") or {}
        if approval.action not in self.delegates or marker.get("task_id") != str(task_id):
            raise ApprovalError(f"approval {approval_id} was not delegated to this task")
        return await self._decide(session, approval_id, outcome=outcome, actor=actor, reason=reason)

    async def _decide(
        self,
        session: AsyncSession,
        approval_id: uuid.UUID,
        *,
        outcome: DecisionOutcome,
        actor: Actor,
        reason: str | None,
    ) -> Approval:
        approval = await session.get(Approval, approval_id, with_for_update=True)
        if approval is None:
            raise ApprovalError(f"approval {approval_id} not found")
        if approval.state != ApprovalState.PENDING:
            raise ApprovalError(f"approval {approval_id} is already {approval.state}")

        await self._release_delegate(session, approval, decided_by=actor)
        approved = outcome == "approve"
        returned = outcome == "revise"
        if returned:
            if not (reason and reason.strip()):
                raise ApprovalError("sending back needs a reason: say what to change")
            if approval.task_id is None or approval.run_id is not None:
                raise ApprovalError("only a decision task can be sent back for changes")
        approval.decided_by = actor.as_json()
        approval.decided_at = self.clock()
        approval.reason = reason
        target = (
            ApprovalState.APPROVED
            if approved
            else ApprovalState.RETURNED
            if returned
            else ApprovalState.REJECTED
        )
        await APPROVAL_FSM.transition(session, approval, target, actor=actor, reason=reason)
        common = {"kind": approval.kind, "ref_type": approval.ref_type, "ref_id": approval.ref_id}
        payload: EventPayload = (
            ev.ApprovalApproved(**common, reason=reason)
            if approved
            else ev.ApprovalReturned(**common, reason=reason or "")
            if returned
            else ev.ApprovalRejected(**common, reason=reason)
        )
        await self._emit(session, approval, payload, actor=actor)
        hook = self.hooks.get(approval.action or "")
        if hook is not None:
            await hook(session, approval, outcome, actor, reason)

        if approval.task_id is None:
            return approval
        task = await session.get(Task, approval.task_id, with_for_update=True)
        if task is None or task.state != TaskState.WAITING_APPROVAL:
            return approval  # the task moved on (cancelled meanwhile): nothing to release
        if returned:
            await self.task_manager.complete_without_run(
                session,
                task,
                {
                    "approval_id": str(approval.id),
                    "decision": "revise",
                    "reason": reason,
                    "returned_by": actor.as_json(),
                },
                output_summary=f"sent back by {actor.id}: {reason}"[:300],
            )
        elif not approved:
            await self.task_manager.cancel(
                session, task, reason=f"approval rejected: {reason or 'no reason given'}"
            )
        elif approval.run_id is not None:
            await self.task_manager.release_after_approval(session, task)
        else:
            await self.task_manager.complete_without_run(
                session,
                task,
                {
                    "approval_id": str(approval.id),
                    "decision": "approve",
                    "approved_by": actor.as_json(),
                },
                output_summary=f"approved by {actor.id}",
            )
        return approval

    async def expire_due(self, session: AsyncSession) -> list[uuid.UUID]:
        """Mark overdue approvals EXPIRED. Their tasks keep waiting (D-001), under a new approval
        (D-131, ``renew_waiting``) — unless the action has a delegate, which gets it first
        (D-157); a delegate that failed, or ran out of time, gives it back to a person."""
        now = self.clock()
        due = (
            await session.scalars(
                select(Approval)
                .where(Approval.state == ApprovalState.PENDING, Approval.expires_at <= now)
                .with_for_update(skip_locked=True)
            )
        ).all()
        expired: list[Approval] = []
        for approval in due:
            if await self._delegate(session, approval):
                continue
            expired.append(approval)
        expired += await self._failed_delegations(session, skip={a.id for a in due})
        for approval in expired:
            await self._release_delegate(session, approval, decided_by=None)
            await APPROVAL_FSM.transition(
                session, approval, ApprovalState.EXPIRED, actor=Actor.system("approvals")
            )
            await self._emit(
                session,
                approval,
                ev.ApprovalExpired(
                    kind=approval.kind, ref_type=approval.ref_type, ref_id=approval.ref_id
                ),
                actor=Actor.system("approvals"),
            )
        await self.renew_waiting(session)
        return [a.id for a in expired]

    async def _delegate(self, session: AsyncSession, approval: Approval) -> bool:
        """Hand an unanswered approval to its action's delegate (D-157), once per approval chain.
        In a savepoint: a delegate that declines or fails leaves it to expire."""
        delegate = self.delegates.get(approval.action or "")
        payload = approval.payload or {}
        if delegate is None or "delegated" in payload or payload.get("delegated_before"):
            return False
        approval_id = approval.id  # a rollback below expires the row's attributes
        try:
            async with session.begin_nested():
                task_id = await delegate(session, approval)
                if task_id is None:
                    return False
                approval.payload = {
                    **payload,
                    "delegated": {"task_id": str(task_id), "at": self.clock().isoformat()},
                }
                approval.expires_at = self.clock() + DELEGATE_WINDOW
                await self._emit(
                    session,
                    approval,
                    ev.ApprovalDelegated(
                        kind=approval.kind,
                        ref_type=approval.ref_type,
                        ref_id=approval.ref_id,
                        task_id=task_id,
                    ),
                    actor=Actor.system("approvals"),
                )
        except Exception:  # noqa: BLE001 - a delegate that cannot start: a person decides
            log.warning("approval %s: could not be delegated", approval_id, exc_info=True)
            await session.refresh(approval)
            return False
        return True

    async def _failed_delegations(
        self, session: AsyncSession, *, skip: set[uuid.UUID]
    ) -> list[Approval]:
        """Delegated approvals still pending whose delegate's task ended without deciding."""
        pending = (
            await session.scalars(
                select(Approval)
                .where(
                    Approval.state == ApprovalState.PENDING,
                    Approval.payload.has_key("delegated"),
                )
                .with_for_update(skip_locked=True)
            )
        ).all()
        out = []
        for approval in pending:
            if approval.id in skip:
                continue
            task = await session.get(Task, uuid.UUID(approval.payload["delegated"]["task_id"]))
            if task is None or task.state in _TASK_DONE:
                out.append(approval)
        return out

    async def _release_delegate(
        self, session: AsyncSession, approval: Approval, *, decided_by: Actor | None
    ) -> None:
        """The approval is settled by someone other than its delegate (a person, or the clock):
        stop the delegate's task if it is still going."""
        marker = (approval.payload or {}).get("delegated")
        if not marker:
            return
        task = await session.get(Task, uuid.UUID(marker["task_id"]), with_for_update=True)
        if task is None or task.state in _TASK_DONE:
            return
        if decided_by is not None and decided_by.kind == "agent":
            return  # the delegate deciding: its own task finishes by itself
        reason = "decided by a person" if decided_by is not None else "no decision in time"
        await self.task_manager.cancel(session, task, reason=reason)

    async def renew_waiting(self, session: AsyncSession) -> list[uuid.UUID]:
        """Ask again for every task still waiting on an approval nobody can decide any more (its
        latest one EXPIRED, none PENDING). Returns the new approvals' ids."""
        waiting = (
            await session.scalars(
                select(Task)
                .where(Task.state == TaskState.WAITING_APPROVAL)
                .with_for_update(skip_locked=True)
            )
        ).all()
        renewed: list[uuid.UUID] = []
        for task in waiting:
            latest = await session.scalar(
                select(Approval)
                .where(Approval.task_id == task.id)
                .order_by(Approval.created_at.desc())
                .limit(1)
            )
            if latest is None or latest.state != ApprovalState.EXPIRED:
                continue  # pending (decidable), or decided and the task is on its way
            again = await self._create(
                session,
                company_id=latest.company_id,
                kind=latest.kind,
                ref_type=latest.ref_type,
                ref_id=latest.ref_id,
                task_id=latest.task_id,
                run_id=latest.run_id,
                action=latest.action,
                payload=_after_delegation(latest.payload or {}),
                summary=latest.summary,
                requested_by=Actor.system("approvals"),
                expires_after=None,
            )
            renewed.append(again.id)
        return renewed

    async def approved_for_run(self, session: AsyncSession, run_id: uuid.UUID) -> list[Approval]:
        """Approvals granted to a run, newest first: what a resumed run is now allowed to do."""
        return list(
            (
                await session.scalars(
                    select(Approval)
                    .where(Approval.run_id == run_id, Approval.state == ApprovalState.APPROVED)
                    .order_by(Approval.decided_at.desc())
                )
            ).all()
        )

    # --- internals -------------------------------------------------------------------------

    async def _create(
        self,
        session: AsyncSession,
        *,
        company_id: uuid.UUID,
        kind: ApprovalKind | str,
        ref_type: str,
        ref_id: uuid.UUID,
        task_id: uuid.UUID | None,
        run_id: uuid.UUID | None,
        action: str | None,
        payload: dict[str, Any],
        summary: str,
        requested_by: Actor,
        expires_after: timedelta | None,
    ) -> Approval:
        existing = await session.scalar(
            select(Approval).where(
                Approval.ref_type == ref_type,
                Approval.ref_id == ref_id,
                Approval.state == ApprovalState.PENDING,
            )
        )
        if existing is not None:
            raise ApprovalError(f"{ref_type} {ref_id} already has a pending approval")
        approval = Approval(
            company_id=company_id,
            kind=kind.value if isinstance(kind, ApprovalKind) else kind,
            ref_type=ref_type,
            ref_id=ref_id,
            task_id=task_id,
            run_id=run_id,
            action=action,
            payload=payload,
            summary=summary,
            requested_by=requested_by.as_json(),
            state=ApprovalState.PENDING.value,
            expires_at=self.clock() + (expires_after or self.default_expiry),
        )
        session.add(approval)
        await session.flush()
        await self._emit(
            session,
            approval,
            ev.ApprovalRequested(
                kind=approval.kind,
                ref_type=ref_type,
                ref_id=ref_id,
                summary=summary,
                expires_at=approval.expires_at,
            ),
            actor=requested_by,
        )
        return approval

    @staticmethod
    async def _emit(
        session: AsyncSession, approval: Approval, payload: EventPayload, *, actor: Actor
    ) -> None:
        await emit(
            session,
            new_event(
                payload,
                company_id=approval.company_id,
                actor=actor,
                aggregate_type="approval",
                aggregate_id=approval.id,
                task_id=approval.task_id,
                run_id=approval.run_id,
            ),
        )


def _after_delegation(payload: dict[str, Any]) -> dict[str, Any]:
    """A renewed approval's payload: no live delegation, but remembering there was one, so it is
    not delegated a second time (D-157)."""
    if "delegated" not in payload:
        return payload
    rest = {k: v for k, v in payload.items() if k != "delegated"}
    return {**rest, "delegated_before": True}
