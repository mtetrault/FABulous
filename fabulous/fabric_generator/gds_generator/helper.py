"""Helper utilities for GDS generation: die area rounding and pitch parsing.

This module exposes utilities used by the GDS generator flows.
"""

import re
from collections import defaultdict
from collections.abc import Iterable
from decimal import Decimal
from fractions import Fraction
from math import gcd
from pathlib import Path
from typing import Any

from librelane.config.config import Config
from librelane.flows.sequential import Substitution, SubstitutionsObject
from librelane.logging.logger import info


def get_layer_info(config: Config) -> dict[str, dict[str, tuple[Decimal, Decimal]]]:
    """Read the FP_TRACKS_INFO file and return layer information.

    Returns a dictionary mapping layer names to their cardinal directions and
    corresponding (offset, pitch) tuples.
    """
    with Path(config["FP_TRACKS_INFO"]).open() as f:
        lines = f.readlines()

    layers: dict[str, dict[str, tuple[Decimal, Decimal]]] = {}
    for line in lines:
        if line.strip() == "":
            continue
        layer, cardinal, offset, pitch = line.split()
        layers[layer] = layers.get(layer) or {}
        layers[layer][cardinal] = (Decimal(offset), Decimal(pitch))

    return layers


def get_pitch(config: Config) -> tuple[Decimal, Decimal]:
    """Read the FP_TRACKS_INFO file and return min pitches for X and Y.

    Returns a tuple (x_pitch, y_pitch) where x_pitch is the minimum pitch along X-axis
    (IO_PIN_V_LAYER X direction) and y_pitch is minimum pitch along Y-axis
    (IO_PIN_H_LAYER Y direction). The cardinal field in FP_TRACKS_INFO is expected to be
    'X' or 'Y' (case-insensitive).
    """
    layers = get_layer_info(config)

    x_pitch = layers[config["IO_PIN_V_LAYER"]]["X"][1]
    y_pitch = layers[config["IO_PIN_H_LAYER"]]["Y"][1]

    return x_pitch, y_pitch


def get_offset(config: Config) -> tuple[Decimal, Decimal]:
    """Read the FP_TRACKS_INFO file and return track offsets for X and Y.

    Returns a tuple (x_offset, y_offset) where x_offset is the track offset along X-axis
    (IO_PIN_V_LAYER X direction) and y_offset is the track offset along Y-axis
    (IO_PIN_H_LAYER Y direction). The cardinal field in FP_TRACKS_INFO is expected to be
    'X' or 'Y' (case-insensitive).
    """
    layers = get_layer_info(config)

    x_offset = layers[config["IO_PIN_V_LAYER"]]["X"][0]
    y_offset = layers[config["IO_PIN_H_LAYER"]]["Y"][0]

    return x_offset, y_offset


def round_up_decimal(value: Decimal, pitch: Decimal) -> Decimal:
    """Round up value to the next multiple of pitch."""
    if pitch == 0:
        return value
    quotient = value // pitch

    remainder = value % pitch
    if remainder > 0:
        quotient += 1
    return quotient * pitch


def lcm_decimal(values: Iterable[Decimal]) -> Decimal:
    """Return the least common multiple of a set of exact decimals.

    For fractions ``a/b`` and ``c/d`` the LCM is ``lcm(a, c) / gcd(b, d)``, so the
    numerators and denominators have to be accumulated separately: letting
    ``Fraction`` normalise an intermediate result discards the denominator.
    """
    numerator, denominator = 1, 0
    for value in values:
        fraction = Fraction(value)
        numerator = numerator * fraction.numerator // gcd(numerator, fraction.numerator)
        denominator = (
            gcd(denominator, fraction.denominator)
            if denominator
            else fraction.denominator
        )
    return Decimal(numerator) / Decimal(denominator)


def get_site_size(config: Config) -> tuple[Decimal, Decimal]:
    """Return the (width, height) of ``PLACE_SITE``, read out of the LEFs.

    FABulous.ExtractPDKInfo publishes the same two numbers as metrics via ODB, but a
    flow's ``run`` needs them before any step has executed, and librelane removed the
    PLACE_SITE_WIDTH / PLACE_SITE_HEIGHT variables that used to carry them, so the
    site block is parsed straight out of the LEF here.
    """
    site = config["PLACE_SITE"]
    candidates: list[str] = [
        str(path) for path in (config.get("TECH_LEFS") or {}).values()
    ]
    candidates += [str(path) for path in (config.get("CELL_LEFS") or [])]

    block = re.compile(
        rf"^\s*SITE\s+{re.escape(site)}\s*$(.*?)^\s*END\s+{re.escape(site)}\b",
        re.MULTILINE | re.DOTALL,
    )
    size = re.compile(r"^\s*SIZE\s+([\d.]+)\s+BY\s+([\d.]+)\s*;", re.MULTILINE)

    seen: set[str] = set()
    for lef in candidates:
        if lef in seen or not Path(lef).is_file():
            continue
        seen.add(lef)
        if (found := block.search(Path(lef).read_text())) and (
            dims := size.search(found.group(1))
        ):
            return Decimal(dims.group(1)), Decimal(dims.group(2))

    raise ValueError(
        f"Placement site '{site}' has no SITE block in TECH_LEFS or CELL_LEFS."
    )


def get_abutment_quantum(
    config: Config,
    site_width: Decimal | None = None,
    site_height: Decimal | None = None,
) -> tuple[Decimal, Decimal]:
    """Return the (x, y) die-dimension quanta that keep abutted tiles aligned.

    A tile placed at a cumulative offset carries its whole grid along with it, so
    every grid a neighbour has to line up with imposes a divisibility constraint on
    this tile's own width and height:

    - the IO pin layers' track pitch, so pins and signal tracks stay in phase;
    - the placement site width, so the standard cell rows - and with them the filler
      cells and the Metal1 followpin rails that only exist inside rows - form one
      continuous array across an east/west seam;
    - twice the site height, because VDD/VSS rail polarity alternates row by row and
      therefore only repeats every second row.

    The site dimensions default to whatever ``PLACE_SITE`` measures in the LEFs;
    pass them explicitly where a step already has them from the metrics.

    Upper metals with a much coarser pitch are deliberately left out. Folding an
    sg13g2 TopMetal1 (2.28) in raises the y quantum from 7.56 to 143.64, inflating
    every tile by tens of microns for a layer that carries no inter-tile signal.
    """
    if site_width is None or site_height is None:
        site_width, site_height = get_site_size(config)
    x_pitch, y_pitch = get_pitch(config)
    return (
        lcm_decimal([x_pitch, site_width]),
        lcm_decimal([y_pitch, 2 * site_height]),
    )


def round_die_dimension(dimension: Decimal, pitch: Decimal, divisions: int) -> Decimal:
    """Round `dimension` up so each of its `divisions` equal parts is pitch-aligned.

    A super tile is split into `divisions` equal parts during IO placement, so
    `dimension / divisions` (not just `dimension`) must be a `pitch` multiple.
    """
    return round_up_decimal(dimension / divisions, pitch) * divisions


def round_die_area(config: Config) -> Config:
    """Round the DIE_AREA to multiples of the minimum pitch.

    This reads the minimum pitch from FP_TRACKS_INFO and updates the config DIE_AREA to
    start at (0,0) with width/height rounded up to the next multiple of that pitch.
    """
    x_pitch, y_pitch = get_pitch(config)

    die_area = config.get("DIE_AREA")
    if die_area is None:
        raise ValueError("DIE_AREA metric not found in state.")
    _, _, width, height = die_area
    width = Decimal(width)
    height = Decimal(height)

    # Round width (X) and height (Y) to the next multiple of the
    # respective minimum pitches using pure Decimal arithmetic

    mWidth = int(config["FABULOUS_TILE_LOGICAL_WIDTH"])
    mHeight = int(config["FABULOUS_TILE_LOGICAL_HEIGHT"])
    width_rounded = round_die_dimension(width, x_pitch, mWidth)
    height_rounded = round_die_dimension(height, y_pitch, mHeight)
    info(
        f"Rounding DIE_AREA from ({width}, {height}) to "
        f"({width_rounded}, {height_rounded}) "
        f"(pitch_x={x_pitch}, pitch_y={y_pitch})"
    )
    return config.copy(DIE_AREA=(0, 0, width_rounded, height_rounded))


def get_routing_obstructions(
    config: Config,
) -> list[tuple[str, Decimal, Decimal, Decimal, Decimal]]:
    """Get the routing obstructions from the config.

    Returns a list of tuples (layer, x1, y1, x2, y2) representing the obstructions in
    the routing area.

    Parameters
    ----------
    config : Config
        The configuration object from liberlane.

    Returns
    -------
    list[tuple[str, Decimal, Decimal, Decimal, Decimal]]
        A list of obstruction tuples.

    Raises
    ------
    ValueError
        If the entry is not a valid obstruction.
    """
    obstructions = config.get("ROUTING_OBSTRUCTIONS") or []
    _, _, width, height = config["DIE_AREA"]
    layers = get_layer_info(config)
    parsed_obstructions = defaultdict(list)
    for obs in obstructions:
        if len(obs) != 5:
            raise ValueError(
                f"Invalid obstruction {obs}. Each obstruction must be a tuple of "
                "the metal layer followed by 4 decimals"
            )
        met, *box = obs
        parsed_obstructions[met].append(box)

    zero = Decimal(0)
    # Add thin obstructions at all the edges
    for layer_name, layer_data in layers.items():
        x_pitch = layer_data["X"][1]
        y_pitch = layer_data["Y"][1]

        # horizontal obstructions
        parsed_obstructions[layer_name].append((zero, -y_pitch / 2, width, zero))
        parsed_obstructions[layer_name].append(
            (zero, height, width, height + y_pitch / 2)
        )

        # vertical obstructions
        parsed_obstructions[layer_name].append((-x_pitch / 2, zero, zero, height))
        parsed_obstructions[layer_name].append(
            (width, zero, width + x_pitch / 2, height)
        )

    result = []
    for layer, boxes in parsed_obstructions.items():
        for box in boxes:
            result.append((layer, *box))

    return result


def merge_layered_substitutions(
    config_sources: list[Any],
) -> SubstitutionsObject | None:
    """Merge `meta.substituting_steps` across layered config sources.

    `Config.load()` overwrites `Config.meta` wholesale for each source in its
    configs list rather than merging, so a later source with no `meta:` key
    (e.g. a tile-specific override dict) silently drops an earlier source's
    `substituting_steps`. This walks the same sources ourselves, in the same
    order, and concatenates each source's own substitutions so a later
    source's entries still apply after an earlier source's.
    """
    merged: list[tuple[str, Substitution]] = []
    for source in config_sources:
        if source is None:
            continue
        if isinstance(source, Path | str):
            if not Path(source).exists():
                # A missing base/override config file is tolerated elsewhere
                # in this flow (Config.load treats it as contributing
                # nothing), so mirror that here instead of letting
                # Config.get_meta's open() raise on a path that legitimately
                # may not exist.
                continue
            # Config.get_meta only special-cases `str`, not other PathLikes.
            source = str(source)
        meta = Config.get_meta(source)
        if not meta.substituting_steps:
            continue
        items = (
            meta.substituting_steps.items()
            if isinstance(meta.substituting_steps, dict)
            else meta.substituting_steps
        )
        merged.extend(items)
    return merged or None
