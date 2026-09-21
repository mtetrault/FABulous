"""Tests for the flow-side half of WhileStep loop substitution."""

import json

import yaml
from librelane.config.variable import Variable
from librelane.flows.sequential import SequentialFlow
from librelane.state.design_format import DesignFormat
from librelane.state.state import State
from librelane.steps.step import Step

from fabulous.fabric_generator.gds_generator.steps.loop_substitution import (
    read_layered_loop_substitutions,
    substitute_loop_steps_in_flow,
)
from fabulous.fabric_generator.gds_generator.steps.while_step import WhileStep

_VAR_NAME = "TEST_LOOP_REPLACEMENT_VAR"


class _InnerStep(Step):
    """Loop-body step that declares no configuration of its own."""

    id = "Test.LoopInner"
    name = "Loop Inner"
    inputs = []  # noqa: RUF012
    outputs = [DesignFormat.NETLIST]  # noqa: RUF012
    config_vars = []  # noqa: RUF012

    def run(self, state_in: State, **kwargs: dict) -> tuple[dict, dict]:  # noqa: D102, ARG002
        return {}, {}


class _ReplacementStep(Step):
    """Loop-body replacement that does declare configuration and an output."""

    id = "Test.LoopReplacement"
    name = "Loop Replacement"
    inputs = []  # noqa: RUF012
    outputs = [DesignFormat.ODB]  # noqa: RUF012
    config_vars = [  # noqa: RUF012
        Variable(_VAR_NAME, str, "Marker variable.", default="unset"),
    ]

    def run(self, state_in: State, **kwargs: dict) -> tuple[dict, dict]:  # noqa: D102, ARG002
        return {}, {}


class _Loop(WhileStep):
    """Loop whose outputs are derived from its body."""

    id = "Test.Loop"
    name = "Loop"
    Steps = [_InnerStep]  # noqa: RUF012


class _LoopWithDeclaredOutputs(WhileStep):
    """Loop that declares its outputs instead of deriving them."""

    id = "Test.LoopDeclared"
    name = "Loop Declared"
    Steps = [_InnerStep]  # noqa: RUF012
    outputs = []  # noqa: RUF012


class _LoopFlow(SequentialFlow):
    Steps = [_Loop]  # noqa: RUF012


class _FlatFlow(SequentialFlow):
    Steps = [_InnerStep]  # noqa: RUF012


def _variable_names(variables: list[Variable]) -> set[str]:
    return {variable.name for variable in variables}


class TestSubstituteLoopStepsInFlow:
    """A substituted loop body must be declared before config resolution."""

    def test_replacement_config_vars_reach_the_composite(self) -> None:
        """WhileStep.Substitute re-derives config_vars from the new body."""
        assert _VAR_NAME not in _variable_names(_Loop.config_vars)

        substituted = _Loop.Substitute({"Test.LoopInner": _ReplacementStep})

        assert _VAR_NAME in _variable_names(substituted.config_vars)
        assert substituted.Steps == [_ReplacementStep]
        assert _Loop.Steps == [_InnerStep], "the original class must be untouched"

    def test_replacement_config_vars_reach_the_flow(self) -> None:
        """The flow's variable list is what Config.load validates against.

        `get_all_config_variables` only reads class attributes, so the class
        stands in for `self` here rather than building a whole flow.
        """
        assert _VAR_NAME not in _variable_names(
            SequentialFlow.get_all_config_variables(_LoopFlow)
        )

        flow_cls = substitute_loop_steps_in_flow(
            _LoopFlow, {"Test.LoopInner": _ReplacementStep}
        )

        assert _VAR_NAME in _variable_names(
            SequentialFlow.get_all_config_variables(flow_cls)
        )
        assert flow_cls.__name__ == _LoopFlow.__name__

    def test_flow_without_a_loop_is_returned_unchanged(self) -> None:
        """Nothing to substitute into means no subclass is made."""
        assert (
            substitute_loop_steps_in_flow(
                _FlatFlow, {"Test.LoopInner": _ReplacementStep}
            )
            is _FlatFlow
        )

    def test_derived_outputs_follow_the_new_body(self) -> None:
        """Views a substituted step produces must still leave the loop."""
        substituted = _Loop.Substitute({"Test.LoopInner": _ReplacementStep})

        assert _Loop.outputs == [DesignFormat.NETLIST]
        assert substituted.outputs == [DesignFormat.ODB]

    def test_declared_outputs_are_preserved(self) -> None:
        """An explicit outputs list is a decision, not a derivation."""
        substituted = _LoopWithDeclaredOutputs.Substitute(
            {"Test.LoopInner": _ReplacementStep}
        )

        assert substituted.outputs == []


class TestReadLayeredLoopSubstitutions:
    """The raw-config read must match what Config.load would have resolved."""

    def test_last_source_that_sets_it_wins(self, tmp_path) -> None:  # noqa: ANN001
        """Config.load replaces a dict-typed variable per source, not merges."""
        base = tmp_path / "base.yaml"
        base.write_text(yaml.safe_dump({"FABULOUS_LOOP_SUBSTITUTE_STEPS": {"A": "B"}}))
        override = tmp_path / "override.json"
        override.write_text(json.dumps({"FABULOUS_LOOP_SUBSTITUTE_STEPS": {"C": "D"}}))

        assert read_layered_loop_substitutions([base, override]) == {"C": "D"}
        assert read_layered_loop_substitutions([override, base]) == {"A": "B"}

    def test_a_mapping_source_is_read_like_a_file(self) -> None:
        """Flows pass override dicts to Config.load alongside paths."""
        assert read_layered_loop_substitutions(
            [{"FABULOUS_LOOP_SUBSTITUTE_STEPS": {"A": "B"}}]
        ) == {"A": "B"}

    def test_a_later_null_clears_an_earlier_value(self, tmp_path) -> None:  # noqa: ANN001
        """Setting the variable to null is how a layer opts out."""
        base = tmp_path / "base.yaml"
        base.write_text(yaml.safe_dump({"FABULOUS_LOOP_SUBSTITUTE_STEPS": {"A": "B"}}))

        assert (
            read_layered_loop_substitutions(
                [base, {"FABULOUS_LOOP_SUBSTITUTE_STEPS": None}]
            )
            is None
        )

    def test_unusable_sources_contribute_nothing(self, tmp_path) -> None:  # noqa: ANN001
        """Missing, empty, non-mapping and .tcl layers are all tolerated."""
        empty = tmp_path / "comments_only.yaml"
        empty.write_text("# nothing here\n")
        sequence = tmp_path / "sequence.yaml"
        sequence.write_text(yaml.safe_dump(["not", "a", "mapping"]))
        tcl = tmp_path / "config.tcl"
        tcl.write_text("set ::env(FABULOUS_LOOP_SUBSTITUTE_STEPS) {}\n")

        assert (
            read_layered_loop_substitutions(
                [None, tmp_path / "absent.yaml", empty, sequence, tcl]
            )
            is None
        )
