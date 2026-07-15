"""Control profiles and the decision engine (P5 core).

A profile places controls at stages with a rollout mode and a match action.
``decide`` maps a stage's findings + mode to a Decision, always recording
both recommended and executed action (D-006). Enforcement — actually
raising the client-safe error — stays in the adapter (enforcer), never here.

Deliberately not here yet: the 13-level precedence resolver and atomic
reload (arrive with multi-profile support, P5 completion), correlation
(P10), transformations (P8).
"""

from __future__ import annotations

from dataclasses import dataclass

from .contracts import Action, Decision, Mode, Stage
from .controls import StageResult


@dataclass(frozen=True, slots=True)
class Placement:
    """One control placed at one stage."""

    control_id: str
    stage: Stage
    mode: Mode
    on_match: Action = Action.DENY
    threshold: float | None = None


@dataclass(frozen=True, slots=True)
class ControlProfile:
    """A named, versioned set of placements. Immutable once built — reload
    means building and atomically swapping a new profile."""

    name: str
    configuration_id: str
    placements: tuple[Placement, ...]

    def controls_for(self, stage: Stage) -> list[Placement]:
        return [
            p
            for p in self.placements
            if p.stage == stage and p.mode is not Mode.DISABLED
        ]


# How each mode translates a recommended action into an executed one.
# OBSERVE swallows everything; ALERT surfaces but allows; SIMULATE_BLOCK
# records the would-be action and allows; CONFIRM gates on approval;
# BLOCK executes the recommendation.
def _execute_for_mode(mode: Mode, recommended: Action) -> Action:
    if recommended is Action.ALLOW:
        return Action.ALLOW
    match mode:
        case Mode.OBSERVE:
            return Action.ALLOW
        case Mode.ALERT:
            return Action.ALERT
        case Mode.SIMULATE_BLOCK:
            return Action.ALLOW
        case Mode.CONFIRM:
            return Action.REQUIRE_APPROVAL
        case Mode.BLOCK:
            return recommended
        case _:  # DISABLED placements never execute; defensive default
            return Action.ALLOW


def decide(
    result: StageResult,
    placement: Placement,
    profile: ControlProfile,
) -> Decision:
    """Interpret one control's findings at one placement.

    A control failure whose policy is DENY overrides mode leniency:
    fail-closed cannot be observed away (platform invariant).
    """
    control_findings = tuple(
        f for f in result.findings if f.control_id == placement.control_id
    )
    matched = any(f.category != "control_failure" for f in control_findings)

    recommended = placement.on_match if matched else Action.ALLOW
    executed = _execute_for_mode(placement.mode, recommended)

    reason_codes: list[str] = []
    if matched:
        reason_codes.extend(
            sorted({f.category.upper() for f in control_findings if f.category != "control_failure"})
        )
    if result.deny_on_failure and placement.control_id in result.failed_controls:
        recommended = Action.DENY
        executed = Action.DENY
        reason_codes.append("CONTROL_FAILURE_FAIL_CLOSED")

    return Decision(
        mode=placement.mode,
        recommended_action=recommended,
        executed_action=executed,
        policy_id=profile.name,
        configuration_id=profile.configuration_id,
        stage=result.stage,
        reason_codes=tuple(reason_codes),
        finding_ids=tuple(f.finding_id for f in control_findings),
    )


def resolve_stage(decisions: list[Decision]) -> Action:
    """The stage's final executed action: most restrictive wins."""
    return Action.resolve([d.executed_action for d in decisions])
