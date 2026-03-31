from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

import yaml
from librelane.config.variable import Variable
from librelane.flows.classic import Classic
from librelane.flows.flow import Flow, FlowException
from librelane.flows.sequential import SequentialFlow
from librelane.logging.logger import err, warn
from librelane.state.state import State
from librelane.steps import odb as Odb
from librelane.steps import openroad as OpenROAD
from librelane.steps.step import Step

from fabulous.fabric_definition.supertile import SuperTile
from fabulous.fabric_definition.tile import Tile
from fabulous.fabric_generator.gds_generator.flows.flow_define import (
    check_steps,
    classic_gating_config_vars,
    physical_steps,
    prep_steps,
    write_out_steps,
)
from fabulous.fabric_generator.gds_generator.helper import (
    get_offset,
    get_pitch,
    get_routing_obstructions,
    round_die_area,
)
from fabulous.fabric_generator.gds_generator.steps.add_buffer import AddBuffers
from fabulous.fabric_generator.gds_generator.steps.custom_pdn import CustomGeneratePDN
from fabulous.fabric_generator.gds_generator.steps.tile_IO_placement import (
    FABulousTileIOPlacement,
)
from fabulous.fabric_generator.gds_generator.steps.tile_optimisation import (
    OptMode,
    TileOptimisation,
)
from fabulous.fabulous_settings import get_context


from fabulous.fabric_generator.gds_generator.flows.tile_macro_flow import (
    FABulousTileVerilogMacroFlow,
)

from fabulous.fabric_generator.gds_generator.steps import innovus as Innovus


subs = {
    # Disable STA
    "OpenROAD.STAPrePNR*": None,
    "OpenROAD.STAMidPNR*": None,
    "OpenROAD.STAPostPNR*": None,
    # IO placement
    "Odb.CustomIOPlacement": FABulousTileIOPlacement,
    # Power
    "OpenROAD.GeneratePDN": CustomGeneratePDN,
    "OpenROAD.Resize*": None,
    "OpenROAD.RepairDesign*": None,
    "+OpenROAD.GlobalPlacement": AddBuffers,
}


configs = Classic.config_vars + [
    Variable(
        "FABULOUS_IGNORE_DEFAULT_DIE_AREA",
        bool,
        "When is true will ignore the provided die area and "
        "use the default one instead.",
        default=False,
    ),
    Variable(
            "MY_VARIABLE_PLACEHOLDER",
            Optional[bool],
            "When is true will ignore the provided die area and "
            "use the default one instead.",
            default=False,
        ),
]

@Flow.factory.register()
class CustomizedTileMacroFlow(FABulousTileVerilogMacroFlow):
    """A tile optimisation flow for FABulous fabric generation from Verilog."""

    Steps = (
        prep_steps
        + [
            TileOptimisation,
            OpenROAD.FillInsertion,
            Odb.CellFrequencyTables,
            OpenROAD.RCX,
            OpenROAD.IRDropReport,
        ]
        #+ write_out_steps
        #+ check_steps
    )

    config_vars = configs

    gating_config_vars = classic_gating_config_vars