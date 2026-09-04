"""Tests for odb_power module - validates coordinate transformation and geometry."""

import sys
from enum import Enum
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from fabulous.fabric_generator.gds_generator.script.odb_power import (
    merge_touching_rects,
    propagate_supply_net,
)


class FakeMetalLayersEnum(Enum):
    METAL1 = 1
    METAL2 = 2
    METAL3 = 3


class GeometryRecorder:
    """Records ODB box creation with actual coordinates for validation."""

    def __init__(self) -> None:
        self.sboxes: list[
            tuple[str, FakeMetalLayersEnum, int, int, int, int]
        ] = []  # net, layer, x1, y1, x2, y2
        self.bboxes: list[
            tuple[str, FakeMetalLayersEnum, int, int, int, int]
        ] = []  # bterm, layer, x1, y1, x2, y2


class FakeGeometry:
    """Mock geometry box with actual dimensions."""

    def __init__(
        self,
        xmin: int,
        ymin: int,
        xmax: int,
        ymax: int,
        techLayer: FakeMetalLayersEnum = FakeMetalLayersEnum.METAL1,
    ) -> None:
        self._xmin = xmin
        self._ymin = ymin
        self._xmax = xmax
        self._ymax = ymax
        self._techLayer = techLayer

    def xMin(self) -> int:  # noqa: N802
        return self._xmin

    def yMin(self) -> int:  # noqa: N802
        return self._ymin

    def xMax(self) -> int:  # noqa: N802
        return self._xmax

    def yMax(self) -> int:  # noqa: N802
        return self._ymax

    def getTechLayer(self) -> FakeMetalLayersEnum:
        return self._techLayer


class FakeMPin:
    """Mock master pin with geometry."""

    def __init__(self, geometries: list[FakeGeometry]) -> None:
        self._geometries = geometries

    def getGeometry(self) -> list[FakeGeometry]:
        return self._geometries


class FakeMTerm:
    """Mock master terminal with pins."""

    def __init__(self, name: str, mpins: list[FakeMPin], sigType: str) -> None:
        self._name = name
        self._mpins = mpins
        self._mtype = sigType

    def getName(self) -> str:
        return self._name

    def getMPins(self) -> list[FakeMPin]:
        return self._mpins

    def getSigType(self) -> list[FakeMPin]:
        return self._mpins


class FakeMaster:
    """Mock master cell with power terminals."""

    def __init__(self, mterms: list[FakeMTerm]) -> None:
        self._mterms = mterms

    def getMTerms(self) -> list[FakeMTerm]:
        return self._mterms


class FakeITerm:
    """Mock instance terminal."""

    def __init__(self, mterm: FakeMTerm) -> None:
        self._mterm = mterm
        self._net = None

    def getMTerm(self) -> FakeMTerm:
        return self._mterm

    def connect(self, net: object) -> None:
        self._net = net


class FakeInst:
    """Mock instance with location and terminals."""

    def __init__(
        self, name: str, location: tuple[int, int], master: FakeMaster
    ) -> None:
        self._name = name
        self._location = location
        self._master = master
        # Create iterms based on master mterms
        self._iterms = [FakeITerm(mterm) for mterm in master.getMTerms()]

    def getName(self) -> str:
        return self._name

    def getLocation(self) -> tuple[int, int]:
        return self._location

    def getMaster(self) -> FakeMaster:
        return self._master

    def getITerms(self) -> list[FakeITerm]:
        return self._iterms


class FakeNet:
    """Mock ODB net."""

    def __init__(self, name: str) -> None:
        self._name = name
        self._sig_type = None
        self._special = False

    def getName(self) -> str:
        return self._name

    def setSpecial(self) -> None:
        self._special = True

    def setSigType(self, sig_type: str) -> None:
        self._sig_type = sig_type

    def getSigType(self) -> str | None:
        return self._sig_type


class FakeBTerm:
    """Mock boundary terminal."""

    def __init__(self, name: str) -> None:
        self._name = name
        self._type = None

    def getName(self) -> str:
        return self._name

    def setIoType(self, io_type: str) -> None:
        pass

    def setSigType(self, sig_type: str | None) -> None:
        self._type = sig_type

    def getSigType(self) -> str:
        return self._type

    def setSpecial(self) -> None:
        pass


class FakeBPin:
    """Mock boundary pin."""

    def __init__(self, bterm: FakeBTerm) -> None:
        self._bterm = bterm
        self._status = None

    def setPlacementStatus(self, status: str) -> None:
        self._status = status


class FakeBlock:
    """Mock ODB block."""

    def __init__(self, instances: list[FakeInst]) -> None:
        self._nets: dict[str, FakeNet] = {}
        self._instances = instances

    def findNet(self, name: str) -> FakeNet | None:
        return self._nets.get(name)

    def getInsts(self) -> list[FakeInst]:
        return self._instances

    def _add_net(self, net: FakeNet) -> None:
        self._nets[net.getName()] = net


class FakeReader:
    """Mock ODB reader."""

    def __init__(self, instances: list[FakeInst]) -> None:
        self.block = FakeBlock(instances)


def make_fake_odb_with_geometry(recorder: GeometryRecorder) -> SimpleNamespace:
    """Create fake ODB that records actual geometry coordinates."""

    def dbNet_create(block: FakeBlock, name: str) -> FakeNet:
        net = FakeNet(name)
        block._add_net(net)  # noqa: SLF001
        return net

    def dbBTerm_create(_net: FakeNet, name: str) -> FakeBTerm:
        return FakeBTerm(name)

    def dbBPin_create(bterm: FakeBTerm) -> FakeBPin:
        return FakeBPin(bterm)

    def dbSWire_create(net: FakeNet, mode: str) -> Mock:
        return Mock(net=net, mode=mode)

    def dbSBox_create(
        wire: Mock,
        _layer: FakeMetalLayersEnum,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        _stripe: str,
    ) -> None:
        recorder.sboxes.append((wire.net.getName(), _layer, x1, y1, x2, y2))

    def dbBox_create(
        bpin: FakeBPin, _layer: FakeMetalLayersEnum, x1: int, y1: int, x2: int, y2: int
    ) -> None:
        recorder.bboxes.append((bpin._bterm.getName(), _layer, x1, y1, x2, y2))  # noqa: SLF001

    return SimpleNamespace(
        dbNet=SimpleNamespace(create=dbNet_create),
        dbSWire=SimpleNamespace(create=dbSWire_create),
        dbBTerm=SimpleNamespace(create=dbBTerm_create),
        dbBPin_create=dbBPin_create,
        dbSBox_create=dbSBox_create,
        dbBox_create=dbBox_create,
    )


def test_power_transforms_coordinates_correctly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that power() correctly transforms geometry coordinates by instance
    location."""
    recorder = GeometryRecorder()
    fake_odb = make_fake_odb_with_geometry(recorder)
    monkeypatch.setitem(sys.modules, "odb", fake_odb)

    # Create instance at (100, 200) with VPWR pin geometry (10, 20, 30, 40)
    vpwr_geom = FakeGeometry(10, 20, 30, 40)
    vpwr_mpin = FakeMPin([vpwr_geom])
    vpwr_mterm = FakeMTerm("VPWR", [vpwr_mpin], "POWER")
    master = FakeMaster([vpwr_mterm])
    inst = FakeInst("tile_0", (100, 200), master)

    reader = FakeReader([inst])

    # Run the power function
    propagate_supply_net(fake_odb, reader, supply_name="VPWR", supply_type="POWER")

    # Verify coordinate transformation: instance_loc + geometry_bbox
    # Expected coords: (100 + 10, 200 + 20, 100 + 30, 200 + 40) = (110, 220, 130, 240)
    vpwr_sboxes = [box for box in recorder.sboxes if box[0] == "VPWR"]
    assert len(vpwr_sboxes) == 1, "Should create one SBox for VPWR"
    assert vpwr_sboxes[0] == ("VPWR", FakeMetalLayersEnum.METAL1, 110, 220, 130, 240), (
        "Incorrect coordinate transformation"
    )

    vpwr_bboxes = [box for box in recorder.bboxes if box[0] == "VPWR"]
    assert len(vpwr_bboxes) == 1, "Should create one BBox for VPWR"
    assert vpwr_bboxes[0] == ("VPWR", FakeMetalLayersEnum.METAL1, 110, 220, 130, 240), (
        "BBox should match SBox coordinates"
    )


def test_power_handles_multiple_instances(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that power() processes multiple instances correctly."""
    recorder = GeometryRecorder()
    fake_odb = make_fake_odb_with_geometry(recorder)
    monkeypatch.setitem(sys.modules, "odb", fake_odb)

    # Create two instances at different locations
    vpwr_geom = FakeGeometry(0, 0, 50, 50)
    vgnd_geom = FakeGeometry(0, 0, 50, 50)

    vpwr_mpin = FakeMPin([vpwr_geom])
    vgnd_mpin = FakeMPin([vgnd_geom])
    vpwr_mterm = FakeMTerm("VPWR", [vpwr_mpin], "POWER")
    vgnd_mterm = FakeMTerm("VGND", [vgnd_mpin], "GROUND")
    master = FakeMaster([vpwr_mterm, vgnd_mterm])

    inst1 = FakeInst("tile_0", (0, 0), master)
    inst2 = FakeInst("tile_1", (100, 100), master)

    reader = FakeReader([inst1, inst2])
    propagate_supply_net(fake_odb, reader, supply_name="VPWR", supply_type="POWER")
    propagate_supply_net(fake_odb, reader, supply_name="VGND", supply_type="GROUND")

    # Should have 2 VPWR boxes (one per instance) and 2 VGND boxes
    vpwr_sboxes = [box for box in recorder.sboxes if box[0] == "VPWR"]
    vgnd_sboxes = [box for box in recorder.sboxes if box[0] == "VGND"]

    assert len(vpwr_sboxes) == 2, "Should create SBox for each instance's VPWR"
    assert len(vgnd_sboxes) == 2, "Should create SBox for each instance's VGND"

    # Verify first instance (at origin)
    assert (FakeMetalLayersEnum.METAL1, 0, 0, 50, 50) in [
        box[1:] for box in vpwr_sboxes
    ]
    # Verify second instance (offset by 100, 100)
    assert (FakeMetalLayersEnum.METAL1, 100, 100, 150, 150) in [
        box[1:] for box in vpwr_sboxes
    ]


def test_power_handles_multiple_geometries_per_pin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that power() creates boxes for all geometries in a pin."""
    recorder = GeometryRecorder()
    fake_odb = make_fake_odb_with_geometry(recorder)
    monkeypatch.setitem(sys.modules, "odb", fake_odb)

    # Create pin with multiple geometry shapes
    geom1 = FakeGeometry(0, 0, 10, 10)
    geom2 = FakeGeometry(20, 20, 30, 30)
    geom3 = FakeGeometry(40, 40, 50, 50)

    vpwr_mpin = FakeMPin([geom1, geom2, geom3])
    vpwr_mterm = FakeMTerm("VPWR", [vpwr_mpin], "POWER")
    master = FakeMaster([vpwr_mterm])
    inst = FakeInst("tile_0", (0, 0), master)

    reader = FakeReader([inst])
    propagate_supply_net(fake_odb, reader, supply_name="VPWR", supply_type="POWER")

    vpwr_sboxes = [box for box in recorder.sboxes if box[0] == "VPWR"]
    assert len(vpwr_sboxes) == 3, "Should create SBox for each geometry"

    # Verify all three geometries are present
    coords = [box[1:] for box in vpwr_sboxes]
    assert (FakeMetalLayersEnum.METAL1, 0, 0, 10, 10) in coords
    assert (FakeMetalLayersEnum.METAL1, 20, 20, 30, 30) in coords
    assert (FakeMetalLayersEnum.METAL1, 40, 40, 50, 50) in coords


def test_power_creates_nets_and_bterms_correctly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that power() creates VPWR/VGND nets and bterms with correct properties."""
    recorder = GeometryRecorder()
    fake_odb = make_fake_odb_with_geometry(recorder)
    monkeypatch.setitem(sys.modules, "odb", fake_odb)

    # Create instance with both VPWR and VGND
    vpwr_geom = FakeGeometry(0, 0, 10, 10)
    vgnd_geom = FakeGeometry(0, 0, 10, 10)
    vpwr_mpin = FakeMPin([vpwr_geom])
    vgnd_mpin = FakeMPin([vgnd_geom])
    vpwr_mterm = FakeMTerm("VPWR", [vpwr_mpin], "POWER")
    vgnd_mterm = FakeMTerm("VGND", [vgnd_mpin], "GROUND")
    master = FakeMaster([vpwr_mterm, vgnd_mterm])
    inst = FakeInst("tile_0", (0, 0), master)

    reader = FakeReader([inst])
    propagate_supply_net(fake_odb, reader, supply_name="VPWR", supply_type="POWER")
    propagate_supply_net(fake_odb, reader, supply_name="VGND", supply_type="GROUND")

    # Verify nets were created
    vpwr_net = reader.block.findNet("VPWR")
    vgnd_net = reader.block.findNet("VGND")

    assert vpwr_net is not None, "VPWR net should be created"
    assert vgnd_net is not None, "VGND net should be created"
    assert vpwr_net.getSigType() == "POWER", "VPWR should have POWER signal type"
    assert vgnd_net.getSigType() == "GROUND", "VGND should have GROUND signal type"


def test_power_connects_iterms_to_nets(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that power() connects instance terminals to power nets."""
    recorder = GeometryRecorder()
    fake_odb = make_fake_odb_with_geometry(recorder)
    monkeypatch.setitem(sys.modules, "odb", fake_odb)

    vpwr_geom = FakeGeometry(0, 0, 10, 10)
    vgnd_geom = FakeGeometry(0, 0, 10, 10)
    vpwr_mpin = FakeMPin([vpwr_geom])
    vgnd_mpin = FakeMPin([vgnd_geom])
    vpwr_mterm = FakeMTerm("VPWR", [vpwr_mpin], "POWER")
    vgnd_mterm = FakeMTerm("VGND", [vgnd_mpin], "GROUND")
    master = FakeMaster([vpwr_mterm, vgnd_mterm])
    inst = FakeInst("tile_0", (0, 0), master)

    reader = FakeReader([inst])
    propagate_supply_net(fake_odb, reader, supply_name="VPWR", supply_type="POWER")
    propagate_supply_net(fake_odb, reader, supply_name="VGND", supply_type="GROUND")

    # Verify iterms are connected to nets
    iterms = inst.getITerms()
    vpwr_iterm = next(it for it in iterms if it.getMTerm().getName() == "VPWR")
    vgnd_iterm = next(it for it in iterms if it.getMTerm().getName() == "VGND")

    assert vpwr_iterm._net is not None, "VPWR iterm should be connected"  # noqa: SLF001
    assert vgnd_iterm._net is not None, "VGND iterm should be connected"  # noqa: SLF001
    assert vpwr_iterm._net.getName() == "VPWR"  # noqa: SLF001
    assert vgnd_iterm._net.getName() == "VGND"  # noqa: SLF001


def test_power_handles_empty_block(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that power() handles blocks with no instances gracefully."""
    recorder = GeometryRecorder()
    fake_odb = make_fake_odb_with_geometry(recorder)
    monkeypatch.setitem(sys.modules, "odb", fake_odb)

    reader = FakeReader([])  # Empty block
    propagate_supply_net(fake_odb, reader, supply_name="VPWR", supply_type="POWER")
    propagate_supply_net(fake_odb, reader, supply_name="VGND", supply_type="GROUND")

    # Should create nets and bterms but no boxes
    assert reader.block.findNet("VPWR") is not None
    assert reader.block.findNet("VGND") is not None
    assert len(recorder.sboxes) == 0, "No SBoxes should be created for empty block"
    assert len(recorder.bboxes) == 0, "No BBoxes should be created for empty block"


def test_power_handles_multiple_metal_layers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that power() creates boxes for all geometries in a pin."""
    recorder = GeometryRecorder()
    fake_odb = make_fake_odb_with_geometry(recorder)
    monkeypatch.setitem(sys.modules, "odb", fake_odb)

    # Create pin with multiple geometry shapes
    geom1 = FakeGeometry(0, 0, 10, 10, techLayer=FakeMetalLayersEnum.METAL1)
    geom2 = FakeGeometry(20, 20, 30, 30, techLayer=FakeMetalLayersEnum.METAL2)
    geom3 = FakeGeometry(40, 40, 50, 50, techLayer=FakeMetalLayersEnum.METAL3)

    vpwr_mpin = FakeMPin([geom1, geom2, geom3])
    vpwr_mterm = FakeMTerm("VPWR", [vpwr_mpin], "POWER")
    master = FakeMaster([vpwr_mterm])
    inst = FakeInst("tile_0", (0, 0), master)

    reader = FakeReader([inst])
    propagate_supply_net(fake_odb, reader, supply_name="VPWR", supply_type="POWER")

    vpwr_sboxes = [box for box in recorder.sboxes if box[0] == "VPWR"]
    assert len(vpwr_sboxes) == 3, "Should create SBox for each geometry"

    # Verify all three geometries are present
    coords = [box[1:] for box in vpwr_sboxes]
    assert (FakeMetalLayersEnum.METAL1, 0, 0, 10, 10) in coords
    assert (FakeMetalLayersEnum.METAL2, 20, 20, 30, 30) in coords
    assert (FakeMetalLayersEnum.METAL3, 40, 40, 50, 50) in coords


def test_power_handles_stacked_metal_layers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that power() creates boxes for all geometries in a pin."""
    recorder = GeometryRecorder()
    fake_odb = make_fake_odb_with_geometry(recorder)
    monkeypatch.setitem(sys.modules, "odb", fake_odb)

    # Create pin with multiple geometry shapes
    geom1 = FakeGeometry(0, 0, 10, 10, techLayer=FakeMetalLayersEnum.METAL1)
    geom2 = FakeGeometry(0, 0, 10, 10, techLayer=FakeMetalLayersEnum.METAL2)
    geom3 = FakeGeometry(0, 0, 10, 10, techLayer=FakeMetalLayersEnum.METAL3)

    vpwr_mpin = FakeMPin([geom1, geom2, geom3])
    vpwr_mterm = FakeMTerm("VPWR", [vpwr_mpin], "POWER")
    master = FakeMaster([vpwr_mterm])
    inst = FakeInst("tile_0", (0, 0), master)

    reader = FakeReader([inst])
    propagate_supply_net(fake_odb, reader, supply_name="VPWR", supply_type="POWER")

    vpwr_sboxes = [box for box in recorder.sboxes if box[0] == "VPWR"]
    assert len(vpwr_sboxes) == 3, "Should create SBox for each geometry"

    # Verify all three geometries are present
    coords = [box[1:] for box in vpwr_sboxes]
    assert (FakeMetalLayersEnum.METAL1, 0, 0, 10, 10) in coords
    assert (FakeMetalLayersEnum.METAL2, 0, 0, 10, 10) in coords
    assert (FakeMetalLayersEnum.METAL3, 0, 0, 10, 10) in coords


class TestMergeTouchingRects:
    """Tests for merge_touching_rects.

    The geometry below is the real RAM_IO seam: a 0.16 x 0.44 um Metal1 rail stub
    published flush against each east/west tile edge, so two abutted tiles meet at
    x = 246.24 um with zero-area contact.
    """

    TILE_W = 246240
    STUB = 160
    RAIL = 440
    Y0, Y1 = 3560, 4000

    def _east(self, tile: int) -> tuple[str, int, int, int, int]:
        x = (tile + 1) * self.TILE_W
        return ("Metal1", x - self.STUB, self.Y0, x, self.Y1)

    def _west(self, tile: int) -> tuple[str, int, int, int, int]:
        x = tile * self.TILE_W
        return ("Metal1", x, self.Y0, x + self.STUB, self.Y1)

    def test_edge_touching_stubs_become_one_shape(self) -> None:
        """The zero-overlap contact between abutted tiles must be coalesced."""
        merged = merge_touching_rects([self._east(0), self._west(1)])

        assert merged == [
            (
                "Metal1",
                self.TILE_W - self.STUB,
                self.Y0,
                self.TILE_W + self.STUB,
                self.Y1,
            )
        ]

    def test_each_seam_merges_independently(self) -> None:
        """One merged shape per seam, in any input order.

        A tile publishes stubs only at its own edges, never the rail spanning its
        interior, so the merged result is one shape per seam rather than one shape
        per row. That is the whole job: bridge the seam with real overlap and leave
        the tile-internal rail to the macro.
        """
        rects = [self._east(0), self._west(1), self._east(1), self._west(2)]
        merged = sorted(merge_touching_rects(list(reversed(rects))))

        assert merged == [
            (
                "Metal1",
                self.TILE_W - self.STUB,
                self.Y0,
                self.TILE_W + self.STUB,
                self.Y1,
            ),
            (
                "Metal1",
                2 * self.TILE_W - self.STUB,
                self.Y0,
                2 * self.TILE_W + self.STUB,
                self.Y1,
            ),
        ]

    def test_keeps_different_rails_apart(self) -> None:
        """Stubs on different rails must not be joined across the y gap."""
        other_rail = (
            "Metal1",
            self.TILE_W,
            self.Y0 + 7560,
            self.TILE_W + self.STUB,
            self.Y1 + 7560,
        )
        merged = merge_touching_rects([self._east(0), self._west(1), other_rail])

        assert len(merged) == 2

    def test_keeps_layers_apart(self) -> None:
        """Touching rects on different layers are not connected and must not merge."""
        _, x0, y0, x1, y1 = self._west(1)
        merged = merge_touching_rects([self._east(0), ("Metal2", x0, y0, x1, y1)])

        assert len(merged) == 2

    def test_leaves_disjoint_stubs_alone(self) -> None:
        """A gap in x must survive - merging it would invent a connection."""
        detached = ("Metal1", self.TILE_W + 1000, self.Y0, self.TILE_W + 1160, self.Y1)
        merged = merge_touching_rects([self._east(0), detached])

        assert len(merged) == 2

    def test_merges_straps_along_y(self) -> None:
        """Straps abut north-to-south, so merging must work on that axis too."""
        lower = ("TopMetal1", 94300, -630, 96500, 250110)
        upper = ("TopMetal1", 94300, 250110, 96500, 500850)

        assert merge_touching_rects([lower, upper]) == [
            ("TopMetal1", 94300, -630, 96500, 500850)
        ]

    def test_absorbs_a_contained_rect(self) -> None:
        """Overlap, not just abutment, must also coalesce."""
        big = ("Metal1", 0, self.Y0, 1000, self.Y1)
        small = ("Metal1", 200, self.Y0, 400, self.Y1)

        assert merge_touching_rects([big, small]) == [big]

    def test_is_idempotent(self) -> None:
        """Re-merging an already merged set must change nothing."""
        rects = [self._east(0), self._west(1), self._east(1), self._west(2)]
        once = merge_touching_rects(rects)

        assert merge_touching_rects(once) == once

    def test_empty_input(self) -> None:
        """No pins is not an error."""
        assert merge_touching_rects([]) == []


def test_power_merges_abutted_tile_stubs(monkeypatch: pytest.MonkeyPatch) -> None:
    """End to end: two abutted instances must yield one merged SBox and BBox."""
    recorder = GeometryRecorder()
    fake_odb = make_fake_odb_with_geometry(recorder)
    monkeypatch.setitem(sys.modules, "odb", fake_odb)

    # A tile 1000 wide publishing a rail stub flush against each vertical edge.
    stubs = [FakeGeometry(0, 100, 40, 140), FakeGeometry(960, 100, 1000, 140)]
    mterm = FakeMTerm("VPWR", [FakeMPin(stubs)], "POWER")
    master = FakeMaster([mterm])
    reader = FakeReader(
        [FakeInst("tile_0", (0, 0), master), FakeInst("tile_1", (1000, 0), master)]
    )

    propagate_supply_net(fake_odb, reader, supply_name="VPWR", supply_type="POWER")

    boxes = sorted(box[1:] for box in recorder.sboxes if box[0] == "VPWR")
    assert boxes == [
        # outer west edge of the array - nothing to abut
        (FakeMetalLayersEnum.METAL1, 0, 100, 40, 140),
        # the seam: tile_0's east stub and tile_1's west stub, now one shape
        (FakeMetalLayersEnum.METAL1, 960, 100, 1040, 140),
        # outer east edge of the array
        (FakeMetalLayersEnum.METAL1, 1960, 100, 2000, 140),
    ], "the seam pair should coalesce; the two outer stubs should be left alone"
    assert sorted(box[1:] for box in recorder.bboxes if box[0] == "VPWR") == boxes, (
        "the top-level pin must carry the same merged geometry"
    )
