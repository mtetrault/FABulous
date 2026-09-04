"""FABulous GDS Generator - assembled-fabric power grid check."""

from importlib import resources
from pathlib import Path
from typing import Any

from librelane.config.flow import option_variables, pdk_variables
from librelane.state.design_format import DesignFormat
from librelane.state.state import State
from librelane.steps.openroad import OpenROADStep
from librelane.steps.step import MetricsUpdate, Step, StepError, ViewsUpdate

_supply_variables = [
    v
    for v in (*option_variables, *pdk_variables)
    if v.name in ("VDD_NETS", "GND_NETS", "VDD_PIN", "GND_PIN")
]


def count_violations(report: Path) -> int:
    """Count the violation lines in a ``check_power_grid`` error report.

    A missing or blank file counts as zero. Note that blank is also what the tool
    writes when it finds no nodes at all, and it does not distinguish the two - see
    ``CheckPowerGrid``.
    """
    if not report.exists():
        return 0
    return sum(1 for line in report.read_text().splitlines() if line.strip())


@Step.factory.register()
class CheckPowerGrid(OpenROADStep):
    """Check the stitched fabric's power grid for islands.

    The fabric flow substitutes ``OpenROAD.GeneratePDN`` for ``Odb.FABulousPDN``,
    which means ``openroad/pdn.tcl`` - the only place LibreLane runs
    ``check_power_grid`` - never executes at fabric level. Without this step an
    unconnected supply shape in the assembled fabric is reported by nothing.

    Known blind spot, inherited from the tool: ``check_power_grid`` writes an empty
    report both when the grid is clean and when it finds no nodes at all, so an
    empty report is necessary but not sufficient. Pair it with the merged-shape
    count that ``odb_power.py`` logs, which is zero if nothing was stitched.
    """

    id = "FABulous.CheckPowerGrid"
    name = "Check Power Grid"
    long_name = "Check Assembled Fabric Power Grid"

    inputs = [DesignFormat.ODB]
    outputs = []

    config_vars = OpenROADStep.config_vars + _supply_variables

    def get_script_path(self) -> str:
        """Return the path to the check_power_grid TCL script."""
        return str(
            resources.files("fabulous.fabric_generator.gds_generator.script")
            / "check_power_grid.tcl"
        )

    def run(
        self,
        state_in: State,
        **kwargs: Any,  # noqa: ANN401
    ) -> tuple[ViewsUpdate, MetricsUpdate]:
        """Run the check and turn each net's report into a metric."""
        views_updates, metrics_updates = super().run(state_in, **kwargs)

        # Same fallback as odb_power.py and set_power_nets.tcl: the *_NETS lists
        # are optional and collapse to the single *_PIN when unset.
        nets = (self.config["VDD_NETS"] or [self.config["VDD_PIN"]]) + (
            self.config["GND_NETS"] or [self.config["GND_PIN"]]
        )
        offenders: list[str] = []
        total = 0
        for net in nets:
            count = count_violations(Path(self.step_dir) / f"{net}-grid-errors.rpt")
            metrics_updates[f"fabulous__power_grid_violation__count__net:{net}"] = count
            total += count
            if count:
                offenders.append(f"{net} ({count})")

        metrics_updates["fabulous__power_grid_violation__count"] = total
        if offenders:
            raise StepError(
                "Power grid check found unconnected shapes on: "
                + ", ".join(offenders)
                + f". See the per-net reports in {self.step_dir}."
            )
        return views_updates, metrics_updates
