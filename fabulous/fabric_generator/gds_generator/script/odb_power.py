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
# Copyright (c) 2026 FABulous Contributors
# SPDX-License-Identifier: Apache-2.0
#

from collections import defaultdict
from typing import Any

import click
import odb as design_odb
from librelane.logging.logger import info
from librelane.scripts.odbpy.reader import click_odb


@click.option(
    "--power-names",
    default=None,
    type=str,
    multiple=True,
    help="The name(s) of the power port(s). Repeat the option for multiple ports.",
)
@click.option(
    "--ground-names",
    default=None,
    type=str,
    multiple=True,
    help="The name(s) of the ground port(s). Repeat the option for multiple ports.",
)
@click.command()
@click_odb
def power(
    reader: Any,  # noqa: ANN401
    power_names: tuple[str],
    ground_names: tuple[str],
) -> None:
    """Cycle through VDD_NETS and GND_NETS for the tiles using a custom script."""
    info(f"propagated VDD_NETS are {power_names}")
    info(f"propagated GND_NETS are {ground_names}")

    # todo: run on multi-power test case
    # odb argument here enables pytest with monkeypatch
    for power_name in power_names:
        propagate_supply_net(design_odb, reader, power_name, "POWER")

    for ground_name in ground_names:
        propagate_supply_net(design_odb, reader, ground_name, "GROUND")


def _layer_key(layer: Any) -> Any:  # noqa: ANN401
    """Return a hashable identity for a tech layer.

    Real ODB hands back a fresh SWIG proxy per query, so two rectangles on the
    same layer need not compare equal; the layer name is stable where it exists.
    """
    getter = getattr(layer, "getName", None)
    return getter() if callable(getter) else layer


def _sweep_merge(
    rects: list[tuple[int, int, int, int]], along_x: bool
) -> list[tuple[int, int, int, int]]:
    """Coalesce rectangles that are colinear and touching/overlapping on one axis."""
    lo = (lambda r: r[0]) if along_x else (lambda r: r[1])
    hi = (lambda r: r[2]) if along_x else (lambda r: r[3])
    groups: dict[tuple[int, int], list[tuple[int, int, int, int]]] = defaultdict(list)
    for rect in rects:
        groups[(rect[1], rect[3]) if along_x else (rect[0], rect[2])].append(rect)

    merged: list[tuple[int, int, int, int]] = []
    for fixed, group in groups.items():
        current = None
        for rect in sorted(group, key=lo):
            if current is not None and lo(rect) <= hi(current):
                if hi(rect) > hi(current):
                    current = (
                        (current[0], fixed[0], hi(rect), fixed[1])
                        if along_x
                        else (fixed[0], current[1], fixed[1], hi(rect))
                    )
                continue
            if current is not None:
                merged.append(current)
            current = rect
        if current is not None:
            merged.append(current)
    return merged


def merge_touching_rects(
    rects: list[tuple[Any, int, int, int, int]],
) -> list[tuple[Any, int, int, int, int]]:
    """Coalesce same-layer rectangles that touch or overlap along one axis.

    Each macro's PG pin geometry is copied verbatim, so two abutted tiles
    contribute two rectangles that share only an edge - a zero-area contact that a
    connectivity or extraction tool is not obliged to read as connected. Merging
    colinear touching rectangles turns a row of per-tile stubs into one continuous
    shape without inventing any geometry.

    Merging runs along x first, for the rails that abut east-to-west, then along y
    for the straps that abut north-to-south.
    """
    by_layer: dict[Any, tuple[Any, list[tuple[int, int, int, int]]]] = {}
    for layer, x0, y0, x1, y1 in rects:
        key = _layer_key(layer)
        by_layer.setdefault(key, (layer, []))[1].append((x0, y0, x1, y1))

    out: list[tuple[Any, int, int, int, int]] = []
    for layer, boxes in by_layer.values():
        coalesced = _sweep_merge(_sweep_merge(boxes, along_x=True), along_x=False)
        out.extend((layer, *box) for box in coalesced)
    return out


def propagate_supply_net(
    layoutDb: Any,  # noqa: ANN401
    reader: Any,  # noqa: ANN401
    supply_name: str,
    supply_type: str,
) -> None:
    """Connect single  power rail for the tiles using a custom script."""
    # Create nets, if they don't exist yet
    net = reader.block.findNet(supply_name)
    if net is None:
        # Create net
        net = layoutDb.dbNet.create(reader.block, supply_name)
        net.setSpecial()
        net.setSigType(supply_type)
        info(f"Created {net.getName()} with type {net.getSigType()}")

    supply_net = reader.block.findNet(supply_name)

    # Create wires
    supply_wire = layoutDb.dbSWire.create(supply_net, "ROUTED")

    # Create bterms (top-level)
    supply_bterm = layoutDb.dbBTerm.create(supply_net, supply_name)
    supply_bterm.setIoType("INOUT")
    supply_bterm.setSigType(supply_net.getSigType())
    supply_bterm.setSpecial()
    supply_bpin = layoutDb.dbBPin_create(supply_bterm)

    # Connect instance-iterms to power nets,
    # draw the wires and pins
    collected: list[tuple[Any, int, int, int, int]] = []
    for blk_inst in reader.block.getInsts():
        info(f"Instance: {blk_inst.getName()}")
        for iterm in blk_inst.getITerms():
            iterm_name = iterm.getMTerm().getName()
            iterm_sigtype = iterm.getMTerm().getSigType()

            if iterm_name == supply_name:
                info(f"Connecting {iterm_name} of type {iterm_sigtype}")
                iterm.connect(supply_net)

        inst_master = blk_inst.getMaster()

        # Now, for each power/ground mterm
        # Collect the geometry of the pins, translated into fabric coordinates
        for master_mterm in inst_master.getMTerms():
            if master_mterm.getName() == supply_name:
                for mterm_mpins in master_mterm.getMPins():
                    for mpins_dbox in mterm_mpins.getGeometry():
                        collected.append(
                            (
                                mpins_dbox.getTechLayer(),
                                blk_inst.getLocation()[0] + mpins_dbox.xMin(),
                                blk_inst.getLocation()[1] + mpins_dbox.yMin(),
                                blk_inst.getLocation()[0] + mpins_dbox.xMax(),
                                blk_inst.getLocation()[1] + mpins_dbox.yMax(),
                            )
                        )

    # Merge before writing: abutted tiles publish PG stubs that meet edge-to-edge,
    # which is a zero-area contact at fabric level (see merge_touching_rects).
    shapes = merge_touching_rects(collected)
    info(f"{supply_name}: {len(collected)} pin rects merged into {len(shapes)} shapes")
    for metal_layer, x_min, y_min, x_max, y_max in shapes:
        layoutDb.dbSBox_create(
            supply_wire, metal_layer, x_min, y_min, x_max, y_max, "STRIPE"
        )
        layoutDb.dbBox_create(supply_bpin, metal_layer, x_min, y_min, x_max, y_max)

    supply_bpin.setPlacementStatus("FIRM")


if __name__ == "__main__":
    power()
