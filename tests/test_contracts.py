"""Contract tests for inference_gate.contracts (P1).

These pin the normative vocabulary: action precedence, mode aliasing
(D-009), tenant-context resolution (fail closed without a tenant), and the
recommended-vs-executed decision split (D-006).
"""

import dataclasses
import types

import pytest

from inference_gate.contracts import (
    Action,
    Decision,
    Finding,
    Mode,
    Severity,
    Stage,
    TenantContext,
)


class TestActionPrecedence:
    def test_deny_beats_everything(self):
        assert Action.resolve([Action.ALLOW, Action.REDACT, Action.DENY]) == Action.DENY

    def test_dehydrate_beats_redact_and_alert(self):
        assert (
            Action.resolve([Action.ALERT, Action.REDACT, Action.DEHYDRATE])
            == Action.DEHYDRATE
        )

    def test_empty_resolves_to_allow(self):
        assert Action.resolve([]) == Action.ALLOW


class TestModeParsing:
    def test_canonical_values_roundtrip(self):
        for mode in Mode:
            assert Mode.parse(mode.value) is mode

    @pytest.mark.parametrize(
        "alias,expected", [("shadow", Mode.OBSERVE), ("review", Mode.ALERT)]
    )
    def test_guard_spec_aliases(self, alias, expected):
        assert Mode.parse(alias) is expected

    @pytest.mark.parametrize("rejected", ["test", "enforce", "on", ""])
    def test_ambiguous_modes_rejected(self, rejected):
        with pytest.raises(ValueError):
            Mode.parse(rejected)


class TestTenantContext:
    def test_maps_user_api_key_auth_fields(self):
        auth = types.SimpleNamespace(
            team_id="team-a",
            org_id="org-1",
            user_id="user-1",
            end_user_id="customer-9",
            api_key="hashed-key-value",
            key_alias="billing-app",
        )
        ctx = TenantContext.from_user_api_key_auth(auth)
        assert ctx.tenant_id == "team-a"
        assert ctx.organization_id == "org-1"
        assert ctx.subject_id == "customer-9"
        assert ctx.virtual_key_id == "hashed-key-value"
        assert ctx.application_id == "billing-app"

    def test_missing_tenant_fails_closed(self):
        with pytest.raises(ValueError, match="no tenant context"):
            TenantContext.from_user_api_key_auth(types.SimpleNamespace(team_id=None))

    def test_context_is_immutable(self):
        ctx = TenantContext(tenant_id="t")
        with pytest.raises(dataclasses.FrozenInstanceError):
            ctx.tenant_id = "other"


class TestDecision:
    def _decision(self, recommended, executed):
        return Decision(
            mode=Mode.SIMULATE_BLOCK,
            recommended_action=recommended,
            executed_action=executed,
            policy_id="enterprise-default",
            configuration_id="cfg-1",
            stage=Stage.REQUEST_CONTEXT,
        )

    def test_simulated_when_actions_differ(self):
        decision = self._decision(Action.DENY, Action.ALLOW)
        assert decision.simulated

    def test_not_simulated_when_enforced(self):
        decision = self._decision(Action.DENY, Action.DENY)
        assert not decision.simulated


class TestFinding:
    def test_finding_ids_are_unique_and_prefixed(self):
        make = lambda: Finding(  # noqa: E731
            control_id="telltale-deterministic",
            category="credential_pattern",
            stage=Stage.REQUEST_CONTEXT,
            severity=Severity.HIGH,
        )
        a, b = make(), make()
        assert a.finding_id.startswith("finding-")
        assert a.finding_id != b.finding_id
