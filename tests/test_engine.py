"""Control executor + decision engine tests (P4/P5 core).

Pins: detection separated from enforcement, failure policy per control
type, mode→executed-action mapping, simulation auditability, and the
invariant that fail-closed control failures cannot be observed away.
"""

import asyncio

import pytest

from inference_gate.contracts import (
    Action,
    ControlType,
    FailureAction,
    Finding,
    Mode,
    Severity,
    Stage,
    TenantContext,
)
from inference_gate.controls import Control, ControlRegistry, execute_stage
from inference_gate.policy import ControlProfile, Placement, decide, resolve_stage

CTX = TenantContext(tenant_id="tenant-a")
STAGE = Stage.REQUEST_CONTEXT


class StaticControl(Control):
    """Emits a fixed finding when armed; raises when broken."""

    def __init__(self, control_id, control_type=ControlType.DETECTOR, *, match=True, error=None):
        self.control_id = control_id
        self.control_type = control_type
        self.match = match
        self.error = error

    async def evaluate(self, segments, tool_calls, stage, context):
        if self.error is not None:
            raise self.error
        if not self.match:
            return []
        return [
            Finding(
                control_id=self.control_id,
                category="credential_pattern",
                stage=stage,
                severity=Severity.HIGH,
            )
        ]


def run_stage(registry, control_ids, **kwargs):
    return asyncio.run(
        execute_stage(registry, control_ids, (), (), STAGE, CTX, **kwargs)
    )


def profile(*placements):
    return ControlProfile(
        name="test-profile", configuration_id="cfg-test", placements=placements
    )


class TestRegistry:
    def test_duplicate_registration_rejected(self):
        registry = ControlRegistry()
        registry.register(StaticControl("a"))
        with pytest.raises(ValueError, match="duplicate"):
            registry.register(StaticControl("a"))

    def test_unknown_control_rejected(self):
        with pytest.raises(KeyError, match="unknown control_id"):
            ControlRegistry().get("ghost")


class TestExecuteStage:
    def test_findings_collected(self):
        registry = ControlRegistry()
        registry.register(StaticControl("det"))
        result = run_stage(registry, ["det"])
        assert len(result.findings) == 1
        assert result.findings[0].category == "credential_pattern"

    def test_detector_failure_fails_open_with_failure_finding(self):
        registry = ControlRegistry()
        registry.register(StaticControl("det", error=RuntimeError("boom")))
        result = run_stage(registry, ["det"])
        assert result.failed_controls == ("det",)
        assert not result.deny_on_failure
        (finding,) = result.findings
        assert finding.category == "control_failure"
        assert "boom" not in str(finding)  # no exception text in findings

    def test_transformer_class_failure_fails_closed(self):
        registry = ControlRegistry()
        registry.register(
            StaticControl("scrub", ControlType.TRANSFORMER, error=RuntimeError("x"))
        )
        result = run_stage(registry, ["scrub"])
        assert result.deny_on_failure

    def test_failure_override_respected(self):
        registry = ControlRegistry()
        registry.register(StaticControl("det", error=RuntimeError("x")))
        result = run_stage(
            registry, ["det"], failure_overrides={"det": FailureAction.DENY}
        )
        assert result.deny_on_failure


class TestDecide:
    def _decision_for(self, mode, *, match=True, control_type=ControlType.DETECTOR, error=None):
        registry = ControlRegistry()
        registry.register(StaticControl("det", control_type, match=match, error=error))
        result = run_stage(registry, ["det"])
        placement = Placement(control_id="det", stage=STAGE, mode=mode)
        return decide(result, placement, profile(placement))

    def test_block_mode_executes_recommendation(self):
        decision = self._decision_for(Mode.BLOCK)
        assert decision.recommended_action == Action.DENY
        assert decision.executed_action == Action.DENY
        assert not decision.simulated

    def test_simulate_block_records_both_actions(self):
        decision = self._decision_for(Mode.SIMULATE_BLOCK)
        assert decision.recommended_action == Action.DENY
        assert decision.executed_action == Action.ALLOW
        assert decision.simulated
        assert "CREDENTIAL_PATTERN" in decision.reason_codes

    def test_observe_mode_allows(self):
        decision = self._decision_for(Mode.OBSERVE)
        assert decision.executed_action == Action.ALLOW

    def test_confirm_mode_requires_approval(self):
        decision = self._decision_for(Mode.CONFIRM)
        assert decision.executed_action == Action.REQUIRE_APPROVAL

    def test_no_match_allows(self):
        decision = self._decision_for(Mode.BLOCK, match=False)
        assert decision.recommended_action == Action.ALLOW
        assert decision.executed_action == Action.ALLOW

    def test_fail_closed_cannot_be_observed_away(self):
        """A DENY-class control failure denies even in OBSERVE mode."""
        decision = self._decision_for(
            Mode.OBSERVE, control_type=ControlType.TRANSFORMER, error=RuntimeError("x")
        )
        assert decision.executed_action == Action.DENY
        assert "CONTROL_FAILURE_FAIL_CLOSED" in decision.reason_codes


class TestResolveStage:
    def test_most_restrictive_decision_wins(self):
        registry = ControlRegistry()
        registry.register(StaticControl("a"))
        registry.register(StaticControl("b", match=False))
        result = run_stage(registry, ["a", "b"])
        placements = [
            Placement(control_id="a", stage=STAGE, mode=Mode.BLOCK),
            Placement(control_id="b", stage=STAGE, mode=Mode.BLOCK),
        ]
        prof = profile(*placements)
        decisions = [decide(result, p, prof) for p in placements]
        assert resolve_stage(decisions) == Action.DENY

    def test_disabled_placements_excluded(self):
        prof = profile(
            Placement(control_id="a", stage=STAGE, mode=Mode.DISABLED),
            Placement(control_id="b", stage=STAGE, mode=Mode.BLOCK),
        )
        assert [p.control_id for p in prof.controls_for(STAGE)] == ["b"]
