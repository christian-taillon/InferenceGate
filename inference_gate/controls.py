"""Control abstraction, registry, and stage executor (P4 core).

A control observes canonical content and returns findings — it never
enforces (D-006). The executor runs the controls a profile places at a
stage, applies the layered failure policy, and hands the findings to the
decision engine (inference_gate.policy).

Transformers (dehydration) extend this in P8; this module deliberately
covers the observe side only.
"""

from __future__ import annotations

import abc
import logging
from dataclasses import dataclass

from .contracts import (
    FAILURE_DEFAULTS,
    ControlType,
    FailureAction,
    Finding,
    Severity,
    Stage,
    TenantContext,
)
from .normalization import TextSegment, ToolCall

logger = logging.getLogger("inference_gate.controls")


class Control(abc.ABC):
    """Base class for detectors, classifiers, and reviewers.

    Implementations must be side-effect free on the content: they observe
    segments and tool calls and return findings. They must never raise to
    signal a detection — raising means the control itself failed and is
    routed through the failure policy.
    """

    control_id: str
    control_type: ControlType

    @abc.abstractmethod
    async def evaluate(
        self,
        segments: tuple[TextSegment, ...],
        tool_calls: tuple[ToolCall, ...],
        stage: Stage,
        context: TenantContext,
    ) -> list[Finding]: ...


class ControlRegistry:
    """Controls keyed by id. Registration is explicit; duplicate ids are a
    configuration error, not a silent override."""

    def __init__(self) -> None:
        self._controls: dict[str, Control] = {}

    def register(self, control: Control) -> None:
        if control.control_id in self._controls:
            raise ValueError(f"duplicate control_id: {control.control_id!r}")
        self._controls[control.control_id] = control

    def get(self, control_id: str) -> Control:
        try:
            return self._controls[control_id]
        except KeyError:
            raise KeyError(f"unknown control_id: {control_id!r}") from None

    def __contains__(self, control_id: str) -> bool:
        return control_id in self._controls


@dataclass(frozen=True, slots=True)
class StageResult:
    """Everything the decision engine needs from one stage execution."""

    stage: Stage
    findings: tuple[Finding, ...]
    failed_controls: tuple[str, ...] = ()
    deny_on_failure: bool = False


async def execute_stage(
    registry: ControlRegistry,
    control_ids: list[str],
    segments: tuple[TextSegment, ...],
    tool_calls: tuple[ToolCall, ...],
    stage: Stage,
    context: TenantContext,
    failure_overrides: dict[str, FailureAction] | None = None,
) -> StageResult:
    """Run the given controls sequentially at a stage.

    Control failures never pass silently: ALLOW_AND_ALERT failures emit a
    control-failure finding and continue; DENY failures mark the result so
    the decision engine denies regardless of content findings.
    """
    findings: list[Finding] = []
    failed: list[str] = []
    deny = False

    for control_id in control_ids:
        control = registry.get(control_id)
        try:
            findings.extend(
                await control.evaluate(segments, tool_calls, stage, context)
            )
        except Exception as exc:
            failed.append(control_id)
            failure_action = (failure_overrides or {}).get(
                control_id,
                FAILURE_DEFAULTS.get(control.control_type, FailureAction.DENY),
            )
            logger.warning(
                "control %s failed at %s (%s); failure action: %s",
                control_id,
                stage,
                type(exc).__name__,
                failure_action,
            )
            findings.append(
                Finding(
                    control_id=control_id,
                    category="control_failure",
                    stage=stage,
                    severity=Severity.HIGH,
                    provenance={"error_type": type(exc).__name__},
                )
            )
            if failure_action is FailureAction.DENY:
                deny = True

    return StageResult(
        stage=stage,
        findings=tuple(findings),
        failed_controls=tuple(failed),
        deny_on_failure=deny,
    )
