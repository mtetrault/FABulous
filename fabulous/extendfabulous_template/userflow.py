"""
To use this example, create a symbolic link in the "fabulous" folder with
"extendfabulous" as link name.

For a custom flow, copy the template elsewhere and similarly create a symbolic link
in the "fabulous" folder.

Alternatively, the extendfabulous python module could be added through
the "pip install -e {module location}" command, where the SelectFlow would
however need to be modified.
"""


from librelane.flows.flow import Flow
from librelane.flows.sequential import SequentialFlow
from librelane.steps import odb as Odb
from librelane.steps import openroad as OpenROAD

from fabulous.fabric_generator.gds_generator.flows.flow_define import (
    check_steps,
    classic_gating_config_vars,
    physical_steps,
    prep_steps,
    write_out_steps,
)

from fabulous.fabric_generator.gds_generator.steps.tile_optimisation import (
    TileOptimisation,
)
from fabulous.fabric_generator.gds_generator.flows.tile_macro_flow import (
    FABulousTileVerilogMacroFlow,
)

from fabulous.fabric_generator.gds_generator.flows.fabric_macro_flow import (
    FABulousFabricMacroFlow,
)



def SelectUserFlow(classtype) -> SequentialFlow | None:

    print(classtype)
    if(classtype ==FABulousTileVerilogMacroFlow):
        print("found match")
        return CustomizedTileMacroFlow


    if(classtype ==FABulousFabricMacroFlow):
        print("found match")
        return CustomizedFabricMacroFlow

    print("no match, returning default flow")
    return classtype


# example user flow modification/override
@Flow.factory.register()
class CustomizedTileMacroFlow(FABulousTileVerilogMacroFlow):
    # Only steps modified here
    Steps = (
        prep_steps
        + [
            TileOptimisation,
            OpenROAD.FillInsertion,
            Odb.CellFrequencyTables,
            #OpenROAD.RCX,
            #OpenROAD.IRDropReport,
        ]
        + write_out_steps
        #+ check_steps
    )

# example user flow modification/override
@Flow.factory.register()
class CustomizedFabricMacroFlow(FABulousFabricMacroFlow):
    """A tile optimisation flow for FABulous fabric generation from Verilog."""
    # Only steps modified here
    #Steps = prep_steps + physical_steps + write_out_steps + check_steps
    Steps = prep_steps + physical_steps + write_out_steps
