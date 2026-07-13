"""Control-plane contracts: the normative v2 vocabulary (P1).

Every control, policy, and telemetry component imports these types; prose
rationale lives in docs/security/OBJECTIVE.md and CONTROL_MODEL.md.

Security invariants encoded here:
- Findings and decisions never carry plaintext secrets or message content —
  only identifiers, categories, scores, spans, and redacted excerpts.
- A decision separates ``recommended_action`` from ``executed_action`` so
  simulation is always auditable (D-006).
- Tenant context is resolved from authenticated LiteLLM identity, never from
  request content (OBJECTIVE: precedence).
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field
from typing import Any


class Stage(enum.StrEnum):
    """Trust-boundary stages (OBJECTIVE.md). LiteLLM hooks are adapters onto
    these; controls are placed per stage, never per hook."""

    INGRESS_REQUEST = "ingress.request"
    REQUEST_NORMALIZED = "request.normalized"
    REQUEST_CONTEXT = "request.context"
    RETRIEVAL_CONTENT = "retrieval.content"
    MCP_METADATA = "mcp.metadata"
    PRE_PROVIDER = "pre_provider"
    PROVIDER_RESPONSE = "provider.response"
    TOOL_CALL_PROPOSED = "tool.call.proposed"
    PRE_TOOL_EXECUTION = "pre_tool_execution"
    TOOL_RESULT = "tool.result"
    MODEL_TO_MODEL = "model_to_model"
    CLIENT_RESPONSE = "client.response"
    STORAGE_EGRESS = "storage.egress"
    CONTROL_PLANE_CHANGE = "control_plane.change"


class ControlType(enum.StrEnum):
    NORMALIZER = "normalizer"
    DECODER = "decoder"
    DETECTOR = "detector"
    CLASSIFIER = "classifier"
    REVIEWER = "reviewer"
    CORRELATOR = "correlator"
    TRANSFORMER = "transformer"
    DECISION_ENGINE = "decision_engine"
    ENFORCER = "enforcer"
    SINK = "sink"


class Mode(enum.StrEnum):
    """Canonical rollout modes. Rollout must progress left to right; never
    jump from development to BLOCK (OBJECTIVE.md, D-009)."""

    DISABLED = "disabled"
    OBSERVE = "observe"
    ALERT = "alert"
    SIMULATE_BLOCK = "simulate-block"
    CONFIRM = "confirm"
    BLOCK = "block"

    @classmethod
    def parse(cls, value: str) -> "Mode":
        """Parse a mode string, accepting guard-spec aliases (D-009).

        ``test`` and ``enforce`` are rejected: ``test`` is offline fixture
        evaluation (not a runtime mode) and ``enforce`` is ambiguous — a
        profile must name simulate-block, confirm, or block explicitly.
        """
        normalized = value.strip().lower()
        aliases = {"shadow": cls.OBSERVE, "review": cls.ALERT}
        if normalized in aliases:
            return aliases[normalized]
        try:
            return cls(normalized)
        except ValueError:
            raise ValueError(
                f"unknown mode {value!r}; canonical modes: "
                f"{[m.value for m in cls]}, aliases: {sorted(aliases)}"
            ) from None


class Action(enum.StrEnum):
    """Enforcement actions, most restrictive first. ``resolve`` implements
    the default precedence; only explicit policy may override it."""

    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"
    QUARANTINE = "quarantine"
    DROP_FIELD = "drop_field"
    DEHYDRATE = "dehydrate"
    REDACT = "redact"
    ROUTE_TO_ALTERNATE = "route_to_alternate"
    ALERT = "alert"
    TAG = "tag"
    ALLOW = "allow"

    @classmethod
    def resolve(cls, actions: "list[Action]") -> "Action":
        """Return the most restrictive action; ALLOW when none given."""
        if not actions:
            return cls.ALLOW
        order = list(cls)
        return min(actions, key=order.index)


class Severity(enum.StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class FailureAction(enum.StrEnum):
    """What a control failure means (timeout, provider down, malformed
    output, parser failure). Layered failure policy replaces the legacy
    global INFERENCE_GATE_FAIL_MODE."""

    ALLOW_AND_ALERT = "allow_and_alert"
    DENY = "deny"
    REVIEW = "review"
    RETRY_ONCE = "retry_once"
    ROUTE_TO_BACKUP = "route_to_backup"
    USE_DETERMINISTIC_ONLY = "use_deterministic_controls_only"


# Defaults per control type (OBJECTIVE.md failure policy). Stage- and
# control-level policy may override, except that transformer/manifest/
# rehydration/final-DLP failures may never be weakened below DENY while the
# feature is enabled (platform invariant).
FAILURE_DEFAULTS: dict[ControlType, FailureAction] = {
    ControlType.DETECTOR: FailureAction.ALLOW_AND_ALERT,
    ControlType.CLASSIFIER: FailureAction.ALLOW_AND_ALERT,
    ControlType.REVIEWER: FailureAction.ALLOW_AND_ALERT,
    ControlType.TRANSFORMER: FailureAction.DENY,
    ControlType.ENFORCER: FailureAction.DENY,
}


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:20]}"


@dataclass(frozen=True, slots=True)
class TenantContext:
    """Trusted identity context, resolved from authenticated LiteLLM
    identity before any control executes. Never populated from request
    content; a missing tenant fails closed at the policy layer.

    ``virtual_key_id`` is LiteLLM's *hashed* key (UserAPIKeyAuth hashes
    api_key in its validator) — never a raw credential.
    """

    tenant_id: str
    virtual_key_id: str | None = None
    organization_id: str | None = None
    user_id: str | None = None
    subject_id: str | None = None
    application_id: str | None = None
    environment: str = "production"
    session_id: str | None = None
    trace_id: str | None = None

    @classmethod
    def from_user_api_key_auth(cls, auth: Any) -> "TenantContext":
        """Map LiteLLM ``UserAPIKeyAuth`` (verified shape, 1.82.0 — see
        LITELLM_CAPABILITY_MATRIX.md) into the trusted context.

        team_id → tenant_id, org_id → organization_id, hashed api_key →
        virtual_key_id, key_alias → application_id, end_user_id → subject_id.
        Raises ValueError when no tenant can be established (fail closed).
        """
        tenant_id = getattr(auth, "team_id", None)
        if not tenant_id:
            raise ValueError("no tenant context: UserAPIKeyAuth has no team_id")
        return cls(
            tenant_id=tenant_id,
            organization_id=getattr(auth, "org_id", None),
            user_id=getattr(auth, "user_id", None),
            subject_id=getattr(auth, "end_user_id", None),
            virtual_key_id=getattr(auth, "api_key", None),  # hashed by litellm
            application_id=getattr(auth, "key_alias", None),
        )


@dataclass(frozen=True, slots=True)
class Finding:
    """A fact observed by a control. Carries no enforcement semantics and no
    plaintext content — ``redacted_excerpt`` must already be safe and
    ``fingerprint`` must be a keyed (HMAC) reference, never an unkeyed hash
    of a secret."""

    control_id: str
    category: str
    stage: Stage
    severity: Severity
    rule_id: str | None = None
    target: str | None = None
    source_path: str | None = None
    span: tuple[int, int] | None = None
    score: float | None = None
    confidence: float | None = None
    redacted_excerpt: str | None = None
    fingerprint: str | None = None
    provenance: dict[str, str] = field(default_factory=dict)
    finding_id: str = field(default_factory=lambda: _new_id("finding"))


@dataclass(frozen=True, slots=True)
class Decision:
    """Policy's interpretation of findings. ``recommended_action`` is what
    policy concluded; ``executed_action`` is what actually happened — they
    differ under OBSERVE/ALERT/SIMULATE_BLOCK, and both are always recorded
    so simulation is auditable."""

    mode: Mode
    recommended_action: Action
    executed_action: Action
    policy_id: str
    configuration_id: str
    stage: Stage
    reason_codes: tuple[str, ...] = ()
    finding_ids: tuple[str, ...] = ()
    decision_id: str = field(default_factory=lambda: _new_id("decision"))

    @property
    def simulated(self) -> bool:
        return self.recommended_action != self.executed_action
