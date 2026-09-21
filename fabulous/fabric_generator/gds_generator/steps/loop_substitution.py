"""Flow-side half of `WhileStep` loop substitution.

`step_substitution` rewrites a loop body; this module gets that rewrite to
happen early enough to matter. `FABULOUS_LOOP_SUBSTITUTE_STEPS` is an ordinary
configuration variable, so `WhileStep.run` can only read it once the flow is
already running -- after `Flow.__init__` has resolved the configuration
against `Flow.get_all_config_variables()`, and after `Step.__init__` has
dropped every value the composite did not declare. A step substituted into a
loop body therefore never sees its own configuration: it silently runs on
defaults.

A flow that reads the variable out of its raw configuration sources and builds
itself out of `substitute_loop_steps_in_flow`'s result instead declares those
variables before resolution, so they survive.
"""

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import yaml
from librelane.flows.flow import Flow
from librelane.flows.sequential import SubstitutionsObject

from fabulous.fabric_generator.gds_generator.steps.while_step import (
    SUBSTITUTE_STEPS_VAR,
    WhileStep,
)

__all__ = ["read_layered_loop_substitutions", "substitute_loop_steps_in_flow"]


def _source_mapping(source: Any) -> Mapping[str, Any] | None:  # noqa: ANN401
    """Read one `Config.load` source as a raw mapping, if it can be one.

    `yaml.safe_load` stands in for LibreLane's own loader, which differs from
    it only in reading floats as `Decimal`; the value read here is a mapping of
    step IDs. A `.tcl` source cannot express the variable, and a file that
    parses to anything but a mapping (a comments-only layer parses to `None`)
    contributes nothing.
    """
    if source is None:
        return None
    if isinstance(source, Mapping):
        return source
    path = Path(source)
    if not path.exists():
        return None
    if path.suffix == ".json":
        parsed = json.loads(path.read_text(encoding="utf8"))
    elif path.suffix in {".yaml", ".yml"}:
        parsed = yaml.safe_load(path.read_text(encoding="utf8"))
    else:
        return None
    return parsed if isinstance(parsed, Mapping) else None


def read_layered_loop_substitutions(
    config_sources: Iterable[Any],
) -> SubstitutionsObject | None:
    """Read `FABULOUS_LOOP_SUBSTITUTE_STEPS` from layered config sources.

    Parameters
    ----------
    config_sources : Iterable[Any]
        The sources `Config.load` is given, lowest precedence first: paths,
        mappings, or `None` for an absent layer.

    Returns
    -------
    SubstitutionsObject | None
        The last source's value, since `Config.load` replaces a `dict`-typed
        variable per source rather than merging it -- so this is the same value
        `WhileStep.run` would have read from the resolved configuration. `None`
        when no source sets it, or when the last one that does sets it to null.
    """
    value: Any = None
    for source in config_sources:
        raw = _source_mapping(source)
        if raw is not None and SUBSTITUTE_STEPS_VAR.name in raw:
            value = raw[SUBSTITUTE_STEPS_VAR.name]
    return value


def substitute_loop_steps_in_flow(
    flow_cls: type[Flow],
    substitutions: SubstitutionsObject,
) -> type[Flow]:
    """Return a flow subclass with `substitutions` applied to its loop bodies.

    Every `WhileStep` in `Steps` is replaced by a `WhileStep.Substitute`
    subclass, so the `config_vars` of the substituted loop-body steps are
    declared by the time `Flow.__init__` resolves the configuration. The flow
    is returned unchanged if it has no `WhileStep`, and keeps its name either
    way so run directories and logs are unaffected.
    """
    steps = list(flow_cls.Steps)
    substituted = [
        step.Substitute(substitutions) if issubclass(step, WhileStep) else step
        for step in steps
    ]
    if substituted == steps:
        return flow_cls
    return type(
        flow_cls.__name__,
        (flow_cls,),
        {
            "Steps": substituted,
            "__module__": flow_cls.__module__,
            "__qualname__": flow_cls.__qualname__,
        },
    )
