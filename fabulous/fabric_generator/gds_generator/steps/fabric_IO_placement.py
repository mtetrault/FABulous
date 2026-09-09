"""FABulous GDS Generator - FABulous I/O Placement Step."""

from decimal import Decimal
from importlib import resources
from typing import Union

from librelane.config import Variable
from librelane.state.state import State
from librelane.steps.odb import OdbpyStep
from librelane.steps.step import (
    MetricsUpdate,
    Step,
    ViewsUpdate,
)

from fabulous.fabric_generator.gds_generator.helper import get_site_size


@Step.factory.register()
class FABulousFabricIOPlacement(OdbpyStep):
    """Stamp fabric-level signal BPins onto their driving/sinking macro pins."""

    id = "Odb.FABulousFabricIOPlacement"
    name = "FABulous fabric I/O Placement"
    long_name = "FABulous fabric I/O Pin Placement Script"

    config_vars = OdbpyStep.config_vars + [
        Variable(
            "FABULOUS_FABRIC_PIN_INSET_ROWS",
            Union[Decimal, tuple[Decimal, Decimal, Decimal, Decimal]],  # noqa: UP007
            "How far a snapped boundary pin is moved back in from the die edge, "
            "in placement rows, either a scalar for all four sides or "
            "(left, bottom, right, top). A pin on the die edge shares that edge "
            "with whatever occupies the FABULOUS_HALO_SPACING band - with the "
            "core opened to the die boundary that is cell rows, their rails, and "
            "the via stacks tying those rails to the mesh, and a pin on a via "
            "site blocks it. Rails sit on row boundaries, so a fractional row "
            "moves the pin into the clear band between two of them: 0.5 is "
            "mid-row. Rows rather than microns because the row is what the "
            "constraint is actually made of, and the site height differs per "
            "PDK while the answer does not.",
            units="rows",
            default=(0, 0, 0, 0),
        ),
    ]

    def get_command(self) -> list[str]:
        """Pass the per-side pin inset through, converted to microns.

        The site height comes from `PLACE_SITE` in the LEFs, the same source
        `get_abutment_quantum` uses, so no per-PDK number has to be written down.
        """
        raw = self.config["FABULOUS_FABRIC_PIN_INSET_ROWS"]
        rows = (raw, raw, raw, raw) if isinstance(raw, Decimal) else raw
        _, site_height = get_site_size(self.config)
        left, bottom, right, top = (Decimal(row) * site_height for row in rows)
        return super().get_command() + [
            "--inset-left",
            str(left),
            "--inset-bottom",
            str(bottom),
            "--inset-right",
            str(right),
            "--inset-top",
            str(top),
        ]

    def get_script_path(self) -> str:
        """Get the path to the I/O placement script."""
        return str(
            resources.files("fabulous.fabric_generator.gds_generator.script")
            / "fabric_io_place.py"
        )

    def run(self, state_in: State, **kwargs: dict) -> tuple[ViewsUpdate, MetricsUpdate]:
        """Place I/O pins using the upstream-compatible stamping strategy."""
        return super().run(state_in, **kwargs)
