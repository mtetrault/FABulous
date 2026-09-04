# Runs OpenROAD's check_power_grid over every supply net of the assembled fabric.
#
# LibreLane normally invokes this from openroad/pdn.tcl, but the fabric flow
# substitutes OpenROAD.GeneratePDN for Odb.FABulousPDN, so pdn.tcl never runs and
# a power-grid island in the stitched fabric would otherwise go unreported.
#
# One report per net, named as pdn.tcl names them so the two are interchangeable
# when comparing a tile run against a fabric run. Each file is pre-created empty:
# check_power_grid writes nothing when it finds no violations, and nothing when it
# finds no nodes at all, so the absence of a file cannot be told from a clean run.
# FABulous.CheckPowerGrid interprets the contents.

source $::env(SCRIPTS_DIR)/openroad/common/io.tcl
read_current_odb

# Resolves VDD_NETS/GND_NETS, falling back to VDD_PIN/GND_PIN when unset - the
# same resolution odb_power.py applies on the Python side.
source $::env(SCRIPTS_DIR)/openroad/common/set_power_nets.tcl

foreach {net} "$::env(VDD_NETS) $::env(GND_NETS)" {
    set report_file $::env(STEP_DIR)/$net-grid-errors.rpt

    set f [open $report_file "w"]
    puts $f ""
    close $f

    if { [catch {check_power_grid -net $net -error_file $report_file} err] } {
        puts stderr "\[WARNING\] Grid check for $net failed: $err"
    }
}
