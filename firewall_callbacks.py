"""Compatibility shim — the shields live in ``inference_gate.shields``.

LiteLLM loads config-file guardrail classes from .py files relative to the
config directory (at litellm 1.82.0, ``get_instance_fn`` has no
installed-package fallback), so this file keeps
``guardrail: firewall_callbacks.<ShieldClass>`` references in config.yaml
working — for this repo and for anyone who copied its config.

New configurations should either ship their own one-line adapter file like
this one, or reference the registered ``inference_gate_*`` provider names —
see README "Bring your own LiteLLM proxy".
"""

from inference_gate.shields import *  # noqa: F401,F403
