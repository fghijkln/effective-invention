read_liberty /workspace/work/omega/synth/pdk/NangateOpenCellLibrary_typical.lib
read_liberty /workspace/work/omega/synth/out/tx_core/mems.lib
read_verilog /workspace/work/omega/synth/out/tx_core/net_buf.v
link_design tx_core
set_wire_load_model -name 5K_hvratio_1_1
create_clock -name clk -period 2.0 [get_ports clk]
set_input_delay 0.1 -clock clk [delete_from_list [all_inputs] [get_ports clk]]
set_output_delay 0.05 -clock clk [all_outputs]
puts "WORST_SLACK [sta::worst_slack_cmd max]"
report_checks -path_delay max -digits 3 -group_path_count 1
puts "REG2REG"
report_checks -path_delay max -from [all_registers -clock_pins] -to [all_registers -data_pins] -digits 3
puts "REG2REG_SLACK [sta::format_time [sta::worst_slack_cmd max] 3]"
exit
