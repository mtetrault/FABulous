"""Place fabric-level signal BPins, halo-aware.

Each fabric-level BTerm connects to one or more tile-macro pins (ITerms) sitting
flush against the fabric boundary. The placement of the BPin is decided per
BTerm from geometry alone:

- The facing side is the master edge the tile pin is flush with (N/S/E/W).
- The gap between that pin edge and the die edge on that side equals the halo
  reserved on that side.
- No halo (gap 0): the pin already touches the die edge, so its geometry is
  stamped in place and needs no routing.
- Halo present (gap > 0): the pin is snapped onto the die edge, leaving the
  router to connect it across the halo. This is how a multi-fanout net such as
  the clock gets a routing channel -- a single edge access box is placed and the
  router fans it out to every sink.
- A multi-fanout net on an abutted (gap 0) side has nowhere to route, so
  placement fails loudly instead of emitting an unroutable design.

The snapped pin can then be moved back inward by a per-side inset. A pin sitting
on the die edge shares that edge with whatever the fabric puts in the halo band:
with the core opened out to the die boundary, the band carries standard cell rows,
their rails, and the via stacks that tie those rails to the mesh. A pin in the way
of a via site blocks it, and the drop to the lowest rail is the one that fails.
Insetting the pin into the space between two rails clears the via sites without
giving up the routing channel the halo exists for. Zero on every side, the
default, leaves placement exactly as described above.
"""

from decimal import Decimal

import click
import odb  # type: ignore[import]
from librelane.logging.logger import info, warn
from librelane.scripts.odbpy.reader import click_odb

from fabulous.fabric_generator.gds_generator.script.odb_protocol import OdbReaderLike


def _facing_side(mterm: object) -> str:
    """Return the master edge (N/S/E/W) the mterm's pins are flush against."""
    bbox = mterm.getBBox()
    master = mterm.getMaster()
    sides = []
    if bbox.xMin() == 0:
        sides.append("WEST")
    if bbox.xMax() == master.getWidth():
        sides.append("EAST")
    if bbox.yMin() == 0:
        sides.append("SOUTH")
    if bbox.yMax() == master.getHeight():
        sides.append("NORTH")
    if len(sides) != 1:
        raise ValueError(
            f"Pin {mterm.getName()} is flush with {sides or 'no'} master edge(s); "
            "a fabric-level pin must sit on exactly one tile edge."
        )
    return sides[0]


def _snap_delta(side: str, iterm: object, die: object) -> tuple[int, int]:
    """Return the (dx, dy) that moves the pin's facing edge onto the die edge."""
    inst_x, inst_y = iterm.getInst().getLocation()
    bbox = iterm.getMTerm().getBBox()
    if side == "SOUTH":
        return 0, die.yMin() - (inst_y + bbox.yMin())
    if side == "NORTH":
        return 0, die.yMax() - (inst_y + bbox.yMax())
    if side == "WEST":
        return die.xMin() - (inst_x + bbox.xMin()), 0
    return die.xMax() - (inst_x + bbox.xMax()), 0


def _inset_delta(side: str, insets: dict[str, int]) -> tuple[int, int]:
    """Return the (dx, dy) that moves a snapped pin inward from the die edge.

    Applied on top of `_snap_delta`, never instead of it, and deliberately not
    folded into it: the abutted-side check tests whether the snap delta is zero,
    which is how it recognises a side with no halo. An inset added before that
    test would make every side look as though it had one.
    """
    if side == "SOUTH":
        return 0, insets["bottom"]
    if side == "NORTH":
        return 0, -insets["top"]
    if side == "WEST":
        return insets["left"], 0
    return -insets["right"], 0


@click.command()
@click.option("--inset-left", default="0", help="Inset from the west die edge, um.")
@click.option("--inset-bottom", default="0", help="Inset from the south die edge, um.")
@click.option("--inset-right", default="0", help="Inset from the east die edge, um.")
@click.option("--inset-top", default="0", help="Inset from the north die edge, um.")
@click_odb
def io_place(
    reader: OdbReaderLike,
    inset_left: str = "0",
    inset_bottom: str = "0",
    inset_right: str = "0",
    inset_top: str = "0",
) -> None:
    """Stamp signal BTerm BPins, snapping to the die edge where a halo exists."""
    stamped = 0
    deleted = 0
    die = reader.block.getDieArea()
    insets = {
        side: int(Decimal(value) * Decimal(reader.dbunits))
        for side, value in (
            ("left", inset_left),
            ("bottom", inset_bottom),
            ("right", inset_right),
            ("top", inset_top),
        )
    }
    if any(insets.values()):
        info(f"Insetting snapped pins from the die edge by {insets} (DBU).")
    for bterm in list(reader.block.getBTerms()):
        if bterm.getSigType() in ("POWER", "GROUND"):
            continue

        net = bterm.getNet()
        if net is None:
            continue

        if bterm.getBPins():
            warn(f"BTerm {bterm.getName()} already has BPin(s); leaving them in place.")
            continue

        iterms = list(net.getITerms())
        if not iterms:
            odb.dbBTerm.destroy(bterm)
            if not net.getITerms() and not net.getBTerms():
                odb.dbNet.destroy(net)
            deleted += 1
            continue

        sides = {_facing_side(iterm.getMTerm()) for iterm in iterms}
        if len(sides) != 1:
            raise ValueError(
                f"BTerm {bterm.getName()} drives sinks on multiple sides {sides}; "
                "cannot place a single boundary pin for it."
            )
        side = next(iter(sides))

        anchor = iterms[0]
        dx, dy = _snap_delta(side, anchor, die)

        if dx == 0 and dy == 0 and len(iterms) > 1:
            raise ValueError(
                f"BTerm {bterm.getName()} drives {len(iterms)} sinks on the abutted "
                f"{side} side with no halo, so the net has nowhere to route. Set "
                "FABULOUS_HALO_SPACING on that side to open a routing channel."
            )

        idx, idy = _inset_delta(side, insets)
        dx, dy = dx + idx, dy + idy

        bpin = odb.dbBPin_create(bterm)
        inst_x, inst_y = anchor.getInst().getLocation()
        for mpin in anchor.getMTerm().getMPins():
            for geom in mpin.getGeometry():
                odb.dbBox_create(
                    bpin,
                    geom.getTechLayer(),
                    inst_x + geom.xMin() + dx,
                    inst_y + geom.yMin() + dy,
                    inst_x + geom.xMax() + dx,
                    inst_y + geom.yMax() + dy,
                )
        bpin.setPlacementStatus("FIRM")
        stamped += 1

    info(f"Stamped {stamped} signal BPins; deleted {deleted} orphan BTerms.")


if __name__ == "__main__":
    io_place()
