"""Tests for the assembled-fabric power grid check."""

from pathlib import Path

from fabulous.fabric_generator.gds_generator.steps.check_power_grid import (
    CheckPowerGrid,
    count_violations,
)


class TestCountViolations:
    """Tests for count_violations."""

    def test_missing_report_is_zero(self, tmp_path: Path) -> None:
        """A step that never wrote a report must not be treated as failing."""
        assert count_violations(tmp_path / "VGND-grid-errors.rpt") == 0

    def test_blank_report_is_zero(self, tmp_path: Path) -> None:
        """check_power_grid.tcl pre-creates each report with a single newline."""
        report = tmp_path / "VGND-grid-errors.rpt"
        report.write_text("\n")

        assert count_violations(report) == 0

    def test_counts_only_non_blank_lines(self, tmp_path: Path) -> None:
        """Blank separator lines in the tool's output must not inflate the count."""
        report = tmp_path / "VPWR-grid-errors.rpt"
        report.write_text("\nViolation: node at (1 2)\n\nViolation: node at (3 4)\n\n")

        assert count_violations(report) == 2


class TestCheckPowerGridStep:
    """Tests for the step's shape, independent of running OpenROAD."""

    def test_reads_odb_and_writes_no_views(self) -> None:
        """The check must not alter the design - it only reports."""
        assert [fmt.id for fmt in CheckPowerGrid.inputs] == ["odb"]
        assert CheckPowerGrid.outputs == []

    def test_declares_the_supply_variables_its_script_reads(self) -> None:
        """check_power_grid.tcl reads all four via set_power_nets.tcl."""
        names = {v.name for v in CheckPowerGrid.config_vars}

        assert {"VDD_NETS", "GND_NETS", "VDD_PIN", "GND_PIN"} <= names

    def test_script_is_packaged(self) -> None:
        """The TCL has to ship with the package, not just exist in the repo."""
        assert Path(CheckPowerGrid.get_script_path(CheckPowerGrid)).is_file()
