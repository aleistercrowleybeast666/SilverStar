# FLIGHT_STATE old-code counter and source review

Base 245bee70c3ee51291b4c875490a5479e8ec553b3. No production change at this checkpoint.

Hardware immutable logs: 159 AIR_RAW frames, no type 0x10/length50 in either GSP radio payload or AIR layer. Actual GSHC parser accepts all159; corrected tuple payload classification is runtime_counts_corrected.json. The first readonly script incorrectly classified the returned tuple rather than its message; its original output is retained, and does not establish message classes. Existing export rejection is consistent with absent source frames, not evidence of GUI dropping FLIGHT_STATE.

Actual generated StreamSend: FLIGHT/RECOVERY, deadline, valid accel/gyro, and initialized published estimator. No GNSS-fix/origin gate. Postflight read snapshots show initialized=1,predict1402,published sequence1403,GNSS-origin=0,baro-origin=1. These are postflight non-atomic reads, not proof of the live telemetry call ordering or latest-IMU flags.

Valid counter v4 uses fresh actual generated TelemetryService, AIR builder, SX1281 transport and driver queues; hardware ports and unrelated subsystem endpoints are Host fixtures. Real normal capacity2,total8, SF10/BW0800/CR4_5,preamble0x18,CRC ON. Exact inherited config frequency2473000000Hz, not2395000000; no RF configuration was changed. Hardware mission cannot be quantitatively reproduced by this virtual IRQ timeline.

Old v4 contended 14005ms: FLIGHT0,NAV_HEALTH58,NAV_CAP12,NAV_PREP12, queued2,streamdeadline0:28187 checks,1 expected failure. NAV-disabled/no-GNSS control:3024/0,7 FLIGHT. No-estimator and no-IMU independent-process controls:3029/0 each,0 FLIGHT,6 NAV. All strict GCC flags including -Werror preserved.

v1/v2 compilation failures, and v3 wrong fixture endpoint/frequency/reset assumptions are retained. They are not evidence of the production defect. v4 corrects those assumptions without production edits. Post-fix expectations will remain unchanged.

Proposed narrow design: alternate preferred normal class after accepted enqueue; failed enqueue cannot count as accepted. Keep control priority, existing periods, queue capacities, format and GNSS-optional mission behavior. Keep missing IMU/estimator rejection. No hardware or COM/DAP access and no mission was performed by this software task. Full source in first_readonly/*.c plus Estimator_GetLatestSnapshot.c and Python parser/handler snapshots.
