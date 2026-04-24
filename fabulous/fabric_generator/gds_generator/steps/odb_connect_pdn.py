"""FABulous GDS Generator - ODB Power Connection Step."""

from importlib import resources

from librelane.steps.common_variables import pdn_variables
from librelane.steps.odb import OdbpyStep
from librelane.steps.step import Step, ViewsUpdate, MetricsUpdate
from librelane.state.state import DesignFormat, State
from typing import (
    Any,
    Dict,
    List,
    Literal,
    Optional,
    Set,
    Tuple,
    TypeAlias,
    Union,
)



@Step.factory.register()
class FABulousPDN(OdbpyStep):
    """Connect power rails for the tiles using a custom script."""

    id = "Odb.FABulousPDN"
    name = "FABulous PDN connections for the tiles"

    config_vars = pdn_variables

    def get_script_path(self) -> str:
        """Get the path to the power connection script."""
        return str(
            resources.files("fabulous.fabric_generator.gds_generator.script")
            / "odb_power.py"
        )

    def get_command(self) -> list[str]:
        """Get the command to run the power connection script."""
        return super().get_command() + [
            "--vmetal-layer-name",
            self.config["PDN_VERTICAL_LAYER"],
            "--hmetal-layer-name",
            self.config["PDN_HORIZONTAL_LAYER"]
        ]

    def run(self, state_in: State, **kwargs) -> Tuple[ViewsUpdate, MetricsUpdate]:
        kwargs, env = self.extract_env(kwargs)

        #if isinstance(self.config["VDD_NETS"], list):

        #    info("Lists of VDD nets not yet supported in FABulous")
        #    assert

        # todo: temp fix and check if list lenght is 1

        # todo: add default value if empty or non-existant

        env["VDD_NETS"] = ''.join(self.config["VDD_NETS"])
        env["GND_NETS"] = ''.join(self.config["GND_NETS"])

        return super().run(state_in, env=env, **kwargs)
