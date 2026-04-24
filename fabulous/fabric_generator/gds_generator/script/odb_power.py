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


@click.option(
    "--vmetal-layer-name",
    default=None,
    type=str,
    help="Metal layer for the vertical power/ground straps",
)
@click.option(
    "--hmetal-layer-name",
    default=None,
    type=str,
    help="Metal layer for the horizontal power/ground straps",
)
@click.command()
@click_odb
def power(
    reader: Any,  # noqa: ANN401
    vmetal_layer_name: str,
    hmetal_layer_name: str,
) -> None:
    """Connect power rails for the tiles using a custom script."""
    # Create ground / power nets
    tech = reader.db.getTech()

    VDD_NET = os.environ.get("VDD_NETS")
    GND_NET = os.environ.get("GND_NETS")
    print(f"propagated VDD_NETS are {VDD_NET}")
    print(f"propagated GND_NETS are {GND_NET}")


    """
    my_vdd_nets = []
    my_vss_nets = []

    for blk_inst in reader.block.getInsts():
        info(f"Instance: {blk_inst.getName()}")
        for iterm in blk_inst.getITerms():
            iterm_name = iterm.getMTerm().getName()
            iterm_sigtype = iterm.getMTerm().getSigType()
            if iterm_sigtype == POWER: #odb.dbSigType.POWER:
                my_vdd_nets.append(net.getName())
            if iterm_sigtype == GROUND: #odb.dbSigType.GROUND:
                my_vss_nets.append(net.getName())

        break

    print("VDD nets:", my_vdd_nets)
    print("VSS nets:", my_vss_nets)
    """

    # begin with supporting only one power domain
    info(f"vmetal_layer_name: {vmetal_layer_name}")
    info(f"hmetal_layer_name: {hmetal_layer_name}")
    vmetal_layer = tech.findLayer(vmetal_layer_name)
    hmetal_layer = tech.findLayer(hmetal_layer_name)

    # Create nets, if they don't exist yet
    # TODO make this generic using VDD_NETS, GND_NETS
    for net_name, net_type in [(VDD_NET, "POWER"), (GND_NET, "GROUND")]:
        net = reader.block.findNet(net_name)
        if net is None:
            # Create net
            net = odb.dbNet.create(reader.block, net_name)
            net.setSpecial()
            net.setSigType(net_type)

    VDD_net = reader.block.findNet(VDD_NET)
    vgnd_net = reader.block.findNet(GND_NET)

    # odb.dbSigType.POWER
    POWER = VDD_net.getSigType()
    # odb.dbSigType.GROUND:
    GROUND = vgnd_net.getSigType()

    # Create wires
    VDD_wire = odb.dbSWire.create(VDD_net, "ROUTED")
    vgnd_wire = odb.dbSWire.create(vgnd_net, "ROUTED")

    # Create bterms (top-level)
    VDD_bterm = odb.dbBTerm.create(VDD_net, VDD_NET)
    VDD_bterm.setIoType("INOUT")
    VDD_bterm.setSigType(VDD_net.getSigType())
    VDD_bterm.setSpecial()
    VDD_bpin = odb.dbBPin_create(VDD_bterm)

    vgnd_bterm = odb.dbBTerm.create(vgnd_net, GND_NET)
    vgnd_bterm.setIoType("INOUT")
    vgnd_bterm.setSigType(vgnd_net.getSigType())
    vgnd_bterm.setSpecial()
    vgnd_bpin = odb.dbBPin_create(vgnd_bterm)

    # Connect instance-iterms to power nets,
    # draw the wires and pins
    for blk_inst in reader.block.getInsts():
        info(f"Instance: {blk_inst.getName()}")
        for iterm in blk_inst.getITerms():
            iterm_name = iterm.getMTerm().getName()
            iterm_sigtype = iterm.getMTerm().getSigType()

            #if iterm_sigtype == POWER:
            if iterm_name == VDD_NET:
                info(f"Connecting power with name {iterm_name}")
                info(f"Signal type is {iterm_sigtype}")
                iterm.connect(VDD_net)

            #if iterm_sigtype == GROUND:
            if iterm_name == GND_NET:
                info(f"Connecting ground with name {iterm_name}")
                info(f"Signal type is {iterm_sigtype}")
                iterm.connect(vgnd_net)

        inst_master = blk_inst.getMaster()

        # Now, for each power/ground mterm (TODO: check signal type instead of name)
        # Copy the geomtry of the pins to wires and top-level pins
        for master_mterm in inst_master.getMTerms():
            if master_mterm.getSigType() == POWER or master_mterm.getSigType() == GROUND:
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
