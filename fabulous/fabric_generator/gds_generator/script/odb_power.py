"""OpenDB script to connect power rails for FABulous fabric."""
#
# Original src: https://github.com/mole99/librelane_plugin_fabulous/blob/main/librelane_plugin_fabulous/scripts/odb_power.py
# OpenDB script for custom Power for FABulous fabric
# This script places vertical PDN straps on top
# of already existing straps in order to tell OpenROAD
# that they should be considered connected and are pins
#
# Copyright (c) 2023 Sylvain Munaut <tnt@246tNt.com>
# Copyright (c) 2025 Leo Moser <leo.moser@pm.me>
# SPDX-License-Identifier: Apache-2.0
#

from typing import Any

import click
import odb
import os
from librelane.logging.logger import info
from librelane.scripts.odbpy.reader import click_odb


@click.command()
@click_odb
def power(
    reader: Any,  # noqa: ANN401
) -> None:

    VDD_NETS = os.environ.get("VDD_NETS").split(' ')
    GND_NETS = os.environ.get("GND_NETS").split(' ')
    info(f"propagated VDD_NETS are {VDD_NETS}")
    info(f"propagated GND_NETS are {GND_NETS}")

    # todo: run on multi-power test case
    for VDD_NET, GND_NET in zip(VDD_NETS, GND_NETS):
        power_pair(reader, VDD_NET, GND_NET)


def power_pair(reader, current_vdd_net, current_gnd_net) -> None:
    """Connect power rails for the tiles using a custom script."""
    # Create ground / power nets
    tech = reader.db.getTech()

    # Create nets, if they don't exist yet
    # todo: review: is this part needed? If no macro has these power nets, no connection will be created.
    for net_name, net_type in [(current_vdd_net, "POWER"), (current_gnd_net, "GROUND")]:
        net = reader.block.findNet(net_name)
        if net is None:
            # Create net
            net = odb.dbNet.create(reader.block, net_name)
            net.setSpecial()
            net.setSigType(net_type)
            info(f"Created {net_name} with type {net_type}")

    VDD_net = reader.block.findNet(current_vdd_net)
    vgnd_net = reader.block.findNet(current_gnd_net)

    # Create wires
    VDD_wire = odb.dbSWire.create(VDD_net, "ROUTED")
    vgnd_wire = odb.dbSWire.create(vgnd_net, "ROUTED")

    # Create bterms (top-level)
    VDD_bterm = odb.dbBTerm.create(VDD_net, current_vdd_net)
    VDD_bterm.setIoType("INOUT")
    VDD_bterm.setSigType(VDD_net.getSigType())
    VDD_bterm.setSpecial()
    VDD_bpin = odb.dbBPin_create(VDD_bterm)

    vgnd_bterm = odb.dbBTerm.create(vgnd_net, current_gnd_net)
    vgnd_bterm.setIoType("INOUT")
    vgnd_bterm.setSigType(vgnd_net.getSigType())
    vgnd_bterm.setSpecial()
    vgnd_bpin = odb.dbBPin_create(vgnd_bterm)

    # until odb.dbSigType.POWER/GROUND are exposed
    POWER  = VDD_net.getSigType()
    GROUND = vgnd_net.getSigType()


    # Connect instance-iterms to power nets,
    # draw the wires and pins
    for blk_inst in reader.block.getInsts():
        info(f"Instance: {blk_inst.getName()}")
        for iterm in blk_inst.getITerms():
            iterm_name = iterm.getMTerm().getName()
            iterm_sigtype = iterm.getMTerm().getSigType()

            #if iterm_sigtype == POWER:
            if iterm_name == current_vdd_net and iterm_sigtype == POWER:
                info(f"Connecting {iterm_name} of type {iterm_sigtype}")
                iterm.connect(VDD_net)

            #if iterm_sigtype == GROUND:
            if iterm_name == current_gnd_net and iterm_sigtype == GROUND:
                info(f"Connecting {iterm_name} of type {iterm_sigtype}")
                iterm.connect(vgnd_net)

        inst_master = blk_inst.getMaster()

        # Now, for each power/ground mterm
        # Copy the geomtry of the pins to wires and top-level pins
        for master_mterm in inst_master.getMTerms():
            if ((master_mterm.getSigType() == POWER or master_mterm.getSigType() == GROUND)
                and
                (master_mterm.getName() == current_vdd_net or master_mterm.getName() == current_gnd_net)):
                for mterm_mpins in master_mterm.getMPins():
                    for mpins_dbox in mterm_mpins.getGeometry():

                        metal_layer = mpins_dbox.getTechLayer()

                        if master_mterm.getSigType() == POWER:
                            odb.dbSBox_create(
                                VDD_wire,
                                metal_layer,
                                blk_inst.getLocation()[0] + mpins_dbox.xMin(),
                                blk_inst.getLocation()[1] + mpins_dbox.yMin(),
                                blk_inst.getLocation()[0] + mpins_dbox.xMax(),
                                blk_inst.getLocation()[1] + mpins_dbox.yMax(),
                                "STRIPE",
                            )
                            odb.dbBox_create(
                                VDD_bpin,
                                metal_layer,
                                blk_inst.getLocation()[0] + mpins_dbox.xMin(),
                                blk_inst.getLocation()[1] + mpins_dbox.yMin(),
                                blk_inst.getLocation()[0] + mpins_dbox.xMax(),
                                blk_inst.getLocation()[1] + mpins_dbox.yMax(),
                            )

                        if master_mterm.getSigType() == GROUND:
                            odb.dbSBox_create(
                                vgnd_wire,
                                metal_layer,
                                blk_inst.getLocation()[0] + mpins_dbox.xMin(),
                                blk_inst.getLocation()[1] + mpins_dbox.yMin(),
                                blk_inst.getLocation()[0] + mpins_dbox.xMax(),
                                blk_inst.getLocation()[1] + mpins_dbox.yMax(),
                                "STRIPE",
                            )
                            odb.dbBox_create(
                                vgnd_bpin,
                                metal_layer,
                                blk_inst.getLocation()[0] + mpins_dbox.xMin(),
                                blk_inst.getLocation()[1] + mpins_dbox.yMin(),
                                blk_inst.getLocation()[0] + mpins_dbox.xMax(),
                                blk_inst.getLocation()[1] + mpins_dbox.yMax(),
                            )

    VDD_bpin.setPlacementStatus("FIRM")
    vgnd_bpin.setPlacementStatus("FIRM")


if __name__ == "__main__":
    power()
