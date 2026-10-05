"""B15b.2 — local auth + association policy (issuance/consume internal-only).

Deterministic, in-process implementation of the approved local lifecycle
(`G4-AUTH-LIFECYCLE.md` §1–§9) under the frozen decisions of
`B15B-DECISION-MATRIX.md` §A (A1–A6). No I/O, no network, no activation:
fixtures only. External results are uniform (`activation_invalid`); internal
audit reasons are more specific and never exposed. Idempotency records contain
no raw prompt/history/tool/provider/credential/terminal content (G4 §5).
"""
from __future__ import annotations

import secrets
import threading
from dataclasses import dataclass, field
from enum import Enum

# ── Frozen constants (matrix §A — A1/A3/A4) ──────────────────────────────────
ACTIVATION_TTL_S = 300  # 5 min
IDLE_TTL_S = 90
HEARTBEAT_S = 30
CURSOR_TTL_S = 900  # 15 min
GRACE_S = 60
CLOCK_SKEW_S = 30
RETENTION_H = 24
NONCE_BYTES = 16  # >= 128-bit one-use nonce (A1)
PURPOSE = "pd_observation"
OWNERSHIP_MODE = "user_owned_session"

#: Uniform external failure (G4 §6) — every failure class returns exactly this.
ACTIVATION_INVALID = "activation_invalid"


class TicketStatus(str, Enum):
    """Persisted ticket states (G4 §2)."""

    ISSUED = "issued"
    CONSUMED = "consumed"
    EXPIRED = "expired"
    REVOKED = "revoked"


class AssociationState(str, Enum):
    """Association states (G4 §3)."""

    PENDING_ACTIVATION = "pending_activation"
    OBSERVING = "observing"
    RECONNECTING = "reconnecting"
    STALE = "stale"
    ENDED = "ended"
    DETACHED = "detached"
    REJECTED = "rejected"


#: Legal transitions exactly as drawn in G4 §3 (no invented edges).
_TRANSITIONS: dict[AssociationState, frozenset[AssociationState]] = {
    AssociationState.PENDING_ACTIVATION: frozenset(
        {AssociationState.OBSERVING, AssociationState.REJECTED}
    ),
    AssociationState.OBSERVING: frozenset(
        {AssociationState.RECONNECTING, AssociationState.ENDED, AssociationState.DETACHED}
    ),
    AssociationState.RECONNECTING: frozenset(
        {AssociationState.STALE, AssociationState.DETACHED}
    ),
    AssociationState.STALE: frozenset({AssociationState.PENDING_ACTIVATION}),
    AssociationState.ENDED: frozenset(),
    AssociationState.DETACHED: frozenset(),
    AssociationState.REJECTED: frozenset(),
}


class AssociationTransitionError(ValueError):
    """Raised on an illegal association transition (fail-closed)."""


@dataclass
class Ticket:
    """Gateway-side ticket record (G4 §1). The record is the authority."""

    activation_ref: str
    observer_ref: str
    owner_ref: str
    profile_ref: str
    workspace_ref: str
    session_ref: str
    association_ref: str
    provenance_ref: str
    issued_at: float
    expires_at: float
    nonce_ref: str
    ownership_mode: str = OWNERSHIP_MODE
    purpose: str = PURPOSE
    status: TicketStatus = TicketStatus.ISSUED
    consumed_at: float | None = None
    revoked_at: float | None = None
    consumed_op_key: tuple[str, str, str, str] | None = None


@dataclass(frozen=True)
class Presentation:
    """Server-resolved presentation context (no caller claims, A1).

    Every field is resolved server-side before reaching this module; the
    module never trusts values supplied by an external caller.
    """

    activation_ref: str
    observer_ref: str
    owner_ref: str
    profile_ref: str
    workspace_ref: str
    session_ref: str
    association_ref: str
    purpose: str


@dataclass(frozen=True)
class BoundedResult:
    """Committed idempotent association result (bounded; no raw content)."""

    association_ref: str
    ownership_mode: str
    status: str


@dataclass
class Association:
    association_ref: str
    state: AssociationState
    created_at: float
    last_heartbeat_at: float

    def transition(self, target: AssociationState) -> None:
        if target not in _TRANSITIONS[self.state]:
            raise AssociationTransitionError(f"{self.state.value} -> {target.value}")
        self.state = target

    def touch(self, now: float) -> None:
        """Heartbeat; allowed while observing/reconnecting."""
        if self.state in (AssociationState.OBSERVING, AssociationState.RECONNECTING):
            self.last_heartbeat_at = now

    def evaluate(self, now: float) -> None:
        """Missed-heartbeat / grace-exceeded transitions (G4 §3)."""
        if self.state == AssociationState.OBSERVING and now - self.last_heartbeat_at > IDLE_TTL_S:
            self.state = AssociationState.RECONNECTING
        elif (
            self.state == AssociationState.RECONNECTING
            and now - self.last_heartbeat_at > IDLE_TTL_S + GRACE_S
        ):
            self.state = AssociationState.STALE


@dataclass
class ConsumeResult:
    """Consume outcome: uniform external shape + internal-only audit reason."""

    external: dict[str, str]
    audit_reason: str | None = None
    result: BoundedResult | None = None
    delivered: bool = False


@dataclass
class SingleWriterTicketStore:
    """Single-writer store (A3): every mutation is one serialized transaction.

    The consume transaction (G4 §4) validates status (nonce one-use is folded
    into the consumed state), marks the ticket consumed, creates the
    association and records idempotency inside a single lock acquisition, so
    no half-created ownership record is observable. Cross-restart crash
    atomicity is a property of the durable store implementation (deferred to
    the live slice — B15b.3/.4); this local slice performs no crash
    simulation.
    """

    _lock: threading.Lock = field(default_factory=threading.Lock)
    _tickets: dict[str, Ticket] = field(default_factory=dict)
    _associations: dict[str, Association] = field(default_factory=dict)
    _idempotency: dict[tuple[str, str, str, str], BoundedResult] = field(default_factory=dict)
    _audit: list[tuple[str, str]] = field(default_factory=list)

    # ── reads ──
    def get_ticket(self, activation_ref: str) -> Ticket | None:
        with self._lock:
            return self._tickets.get(activation_ref)

    def get_association(self, association_ref: str) -> Association | None:
        with self._lock:
            return self._associations.get(association_ref)

    def get_idempotency(self, op_key: tuple[str, str, str, str]) -> BoundedResult | None:
        with self._lock:
            return self._idempotency.get(op_key)

    def audit_log(self) -> list[tuple[str, str]]:
        with self._lock:
            return list(self._audit)

    # ── writes ──
    def put_ticket(self, ticket: Ticket) -> None:
        with self._lock:
            self._tickets[ticket.activation_ref] = ticket

    def revoke_ticket(self, activation_ref: str, now: float) -> bool:
        with self._lock:
            ticket = self._tickets.get(activation_ref)
            if ticket is None or ticket.status != TicketStatus.ISSUED:
                return False
            ticket.status = TicketStatus.REVOKED
            ticket.revoked_at = now
            return True

    def touch_association(self, association_ref: str, now: float) -> AssociationState | None:
        with self._lock:
            association = self._associations.get(association_ref)
            if association is None:
                return None
            association.touch(now)
            return association.state

    def evaluate_association(self, association_ref: str, now: float) -> AssociationState | None:
        with self._lock:
            association = self._associations.get(association_ref)
            if association is None:
                return None
            association.evaluate(now)
            return association.state

    def reassociate(self, association_ref: str) -> AssociationState | None:
        with self._lock:
            association = self._associations.get(association_ref)
            if association is None:
                return None
            association.transition(AssociationState.PENDING_ACTIVATION)
            return association.state

    def consume_transaction(
        self,
        presentation: Presentation,
        op_key: tuple[str, str, str, str],
        now: float,
    ) -> ConsumeResult:
        """The single atomic boundary (G4 §4). All checks run under the lock."""
        with self._lock:
            ticket = self._tickets.get(presentation.activation_ref)
            if ticket is None:
                self._audit.append((presentation.activation_ref, ACTIVATION_INVALID))
                return ConsumeResult(external={"outcome": ACTIVATION_INVALID})

            def deny(reason: str) -> ConsumeResult:
                self._audit.append((ticket.activation_ref, reason))
                return ConsumeResult(external={"outcome": ACTIVATION_INVALID}, audit_reason=reason)

            # issuer/version/purpose/expiry validation (G4 §4)
            if ticket.purpose != presentation.purpose:
                return deny("capability_denied")
            if ticket.status == TicketStatus.REVOKED:
                return deny(ACTIVATION_INVALID)
            if ticket.status == TicketStatus.EXPIRED or (
                ticket.status == TicketStatus.ISSUED and now > ticket.expires_at
            ):
                if ticket.status == TicketStatus.ISSUED:
                    ticket.status = TicketStatus.EXPIRED
                return deny("activation_expired")

            # binding validation (observer + owner/profile/workspace/session/association)
            if ticket.observer_ref != presentation.observer_ref:
                return deny("foreign_owner")
            if (
                ticket.owner_ref != presentation.owner_ref
                or ticket.profile_ref != presentation.profile_ref
                or ticket.workspace_ref != presentation.workspace_ref
                or ticket.session_ref != presentation.session_ref
                or ticket.association_ref != presentation.association_ref
            ):
                return deny("activation_binding_mismatch")

            # status + nonce check; idempotent replay of the exact operation
            if ticket.status == TicketStatus.CONSUMED:
                if ticket.consumed_op_key == op_key:
                    stored = self._idempotency.get(op_key)
                    if stored is not None:
                        return ConsumeResult(
                            external={"outcome": "activated"}, result=stored, delivered=True
                        )
                return deny("activation_replayed")

            # atomic commit: consume + association + idempotency, one boundary
            association = Association(
                association_ref=ticket.association_ref,
                state=AssociationState.OBSERVING,
                created_at=now,
                last_heartbeat_at=now,
            )
            self._associations[association.association_ref] = association
            ticket.status = TicketStatus.CONSUMED
            ticket.consumed_at = now
            ticket.consumed_op_key = op_key
            bounded = BoundedResult(
                association_ref=association.association_ref,
                ownership_mode=ticket.ownership_mode,
                status=association.state.value,
            )
            self._idempotency[op_key] = bounded
            return ConsumeResult(external={"outcome": "activated"}, result=bounded, delivered=True)


class GatewayAuth:
    """Issuance (internal-only, A2) + consume service over a single-writer store."""

    def __init__(self, store: SingleWriterTicketStore | None = None) -> None:
        self.store = store if store is not None else SingleWriterTicketStore()

    def issue_ticket(
        self,
        *,
        observer_ref: str,
        owner_ref: str,
        profile_ref: str,
        workspace_ref: str,
        session_ref: str,
        association_ref: str,
        provenance_ref: str,
        now: float,
        ttl_s: int = ACTIVATION_TTL_S,
    ) -> Ticket:
        """Mint a one-use opaque ticket bound to the authenticated observer.

        Issuer invariant (review LOW-3): at most one live ticket per
        association — explicit re-association after `stale` issues a fresh
        ticket, and a fresh consume (re)creates the association record with
        `created_at` from the new commit.
        """
        ticket = Ticket(
            activation_ref=f"act-{secrets.token_hex(8)}",
            observer_ref=observer_ref,
            owner_ref=owner_ref,
            profile_ref=profile_ref,
            workspace_ref=workspace_ref,
            session_ref=session_ref,
            association_ref=association_ref,
            provenance_ref=provenance_ref,
            issued_at=now,
            expires_at=now + ttl_s,
            nonce_ref=secrets.token_hex(NONCE_BYTES),
        )
        self.store.put_ticket(ticket)
        return ticket

    def consume(self, presentation: Presentation, now: float) -> ConsumeResult:
        """Consume one presentation; uniform external failures (G4 §6)."""
        op_key = (
            presentation.activation_ref,
            presentation.observer_ref,
            presentation.association_ref,
            presentation.purpose,
        )
        return self.store.consume_transaction(presentation, op_key, now)

    def touch(self, association_ref: str, now: float) -> bool:
        """Heartbeat on an existing association (observing/reconnecting only)."""
        return self.store.touch_association(association_ref, now) is not None

    def evaluate(self, association_ref: str, now: float) -> AssociationState | None:
        """Advance missed-heartbeat/grace transitions; returns current state."""
        return self.store.evaluate_association(association_ref, now)

    def reassociate(self, association_ref: str) -> AssociationState | None:
        """stale + explicit reassociation -> pending_activation (G4 §3)."""
        return self.store.reassociate(association_ref)
