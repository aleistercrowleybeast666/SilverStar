set pagination off
set confirm off
set print elements 60
set remotetimeout 3
file D:/python_software/SilverStar/.work/bench08c_f407/Flight_Controller/build/FCCG/SilverStar_F407/Release/auto/SilverStar_0_1_1.elf
target remote 127.0.0.1:3333
monitor reset halt
hbreak *0x080167e6
printf "DIAG_BREAKPOINT_ARMED\n"
continue
printf "REJECTION_HIT\n"
info registers pc lr sp r4 r6 r7
monitor reg primask
bt
info args
info locals
p 'logger_bus.c'::s_initialized
p 'logger_bus.c'::s_accepting_records
p 'logger_bus.c'::s_boot_disabled
p 'logger_bus.c'::s_finalization_state
p 'logger_bus.c'::s_diagnostics
p 'silverstar_flight_cycle.c'::s_lifecycle_state
p pxCurrentTCB
p *pxCurrentTCB
set $reject_payload = *(unsigned int *)($sp + 44)
printf "PAYLOAD_ADDRESS=%#x RECORD_TYPE=%u\n", $reject_payload, $r4
x/32bx $reject_payload
p 'system_log_policy.c'::s_streams
p 'estimator_task.c'::s_estimator.mission_running
p 'estimator_task.c'::s_snapshot.health_flags
p 'silverstar_assert.c'::s_assert_fault
delete breakpoints
monitor resume
printf "DIAG_RESUMED\n"
detach
quit
