# Arty S7-50 XDC Constraints for uhr (clock display)
# Clock: 100 MHz on pin E3
set_property -dict { PACKAGE_PIN E3   IOSTANDARD LVCMOS33 } [get_ports CLK]
create_clock -period 10.000 -name sys_clk_pin -waveform {0.000 5.000} -add [get_ports CLK]

# Reset: BTN0 on pin D9 (active high)
set_property -dict { PACKAGE_PIN D9   IOSTANDARD LVCMOS33 } [get_ports RESET]

# Enable: BTN1 on pin C9 (active high)
set_property -dict { PACKAGE_PIN C9   IOSTANDARD LVCMOS33 } [get_ports ENABLE]

# SECONDS[5:0] -> PMOD JA[1:6] (pins G6, F6, E6, E5, H4, H3)
set_property -dict { PACKAGE_PIN G6   IOSTANDARD LVCMOS33 } [get_ports {SECONDS[5]}]
set_property -dict { PACKAGE_PIN F6   IOSTANDARD LVCMOS33 } [get_ports {SECONDS[4]}]
set_property -dict { PACKAGE_PIN E6   IOSTANDARD LVCMOS33 } [get_ports {SECONDS[3]}]
set_property -dict { PACKAGE_PIN E5   IOSTANDARD LVCMOS33 } [get_ports {SECONDS[2]}]
set_property -dict { PACKAGE_PIN H4   IOSTANDARD LVCMOS33 } [get_ports {SECONDS[1]}]
set_property -dict { PACKAGE_PIN H3   IOSTANDARD LVCMOS33 } [get_ports {SECONDS[0]}]

# MINUTES[5:0] -> PMOD JA[7:8] + JB[1:4] (pins J2, J1, K1, K2, L1, L2)
set_property -dict { PACKAGE_PIN J2   IOSTANDARD LVCMOS33 } [get_ports {MINUTES[5]}]
set_property -dict { PACKAGE_PIN J1   IOSTANDARD LVCMOS33 } [get_ports {MINUTES[4]}]
set_property -dict { PACKAGE_PIN K1   IOSTANDARD LVCMOS33 } [get_ports {MINUTES[3]}]
set_property -dict { PACKAGE_PIN K2   IOSTANDARD LVCMOS33 } [get_ports {MINUTES[2]}]
set_property -dict { PACKAGE_PIN L1   IOSTANDARD LVCMOS33 } [get_ports {MINUTES[1]}]
set_property -dict { PACKAGE_PIN L2   IOSTANDARD LVCMOS33 } [get_ports {MINUTES[0]}]

# HOURS[4:0] -> PMOD JB[5:8] + LED0 (pins L3, L4, L5, L6, H5)
set_property -dict { PACKAGE_PIN L3   IOSTANDARD LVCMOS33 } [get_ports {HOURS[4]}]
set_property -dict { PACKAGE_PIN L4   IOSTANDARD LVCMOS33 } [get_ports {HOURS[3]}]
set_property -dict { PACKAGE_PIN L5   IOSTANDARD LVCMOS33 } [get_ports {HOURS[2]}]
set_property -dict { PACKAGE_PIN L6   IOSTANDARD LVCMOS33 } [get_ports {HOURS[1]}]
set_property -dict { PACKAGE_PIN H5   IOSTANDARD LVCMOS33 } [get_ports {HOURS[0]}]