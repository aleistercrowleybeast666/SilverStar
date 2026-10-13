# Serial maintenance 0.1

Version 0.1 retains every existing 0.0 command, request parameter, response and
error path. The old profile remains selectable. The extension is
`SYSTEM DIAG` (capabilities) and `SYSTEM DIAG <cursor>` (one read-only entry per
page). There is no arbitrary variable, address, symbol or write operation.
The separately negotiated LOGFILE service remains version 1; SSLOG remains 0.0.

Diagnostics schema 1 has fixed groups task/thread/sensor/storage/communication,
stable string IDs, bounded names/reasons, state/source, age and optional counters,
units, progress and meaningful-work/data ages. The current firmware has seven
entries; max_entries is 16 and max_line is 511 bytes. Cursor starts at zero; end=1
terminates enumeration. Clients must reject unsupported critical versions and
duplicate IDs/cursors, bound allocations, ignore unknown optional fields and
display unknown states as unknown. Poll no faster than one complete cycle/second.
Samples from different entries are independent; one response does not imply an
atomic system snapshot. UINT32_MAX age means unavailable, not zero.

Only RAM getters are used. Logger completed-write count/time advances only after
the entire sink write returns success; it is not proof of sync/durability.
Estimator/INS timestamps describe data/state time, not scheduler completion.
Storage write_count includes attempts. No generic task health is inferred from
RTOS task existence or an iteration counter. Missing completion instrumentation
is explicitly UNKNOWN. Downloads share one host serial owner and suspend polling;
the diagnostic rows are cleared with a paused message while any retained status
sample continues aging. No view pretends suspended polling is live.
