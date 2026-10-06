# Background task retirement candidate

The controller now owns WorkerSignals in the GUI thread and uses a private
single-task QThreadPool. All five dispatch slots have typed queued connections
and validate the active sender. Logical finished emission does not release the
runnable: retirement waits for pool.waitForDone(0), then disconnects controller
connections, clears callable references in the GUI thread and uses deleteLater
for signals. Closing and nested save waits use taskSettled after retirement.
Result/error/cancellation publication may enter a nested event loop; retirement
also waits for that publication to return. Cancellation after atomic project
commit continues to publish the committed project state.

This repairs the separately demonstrated finished-before-return gap. It does
not establish the identity of the object collected in the previous Linux/Windows
segfaults. An original MainWindow Windows probe found all five old slots already
executed in the GUI thread; this change makes the contract explicit, rather than
claiming all previous plain methods ran in the wrong thread.

Scoped pre-fix _Task_Finish injection from c1b2669 failed the held-return test
(1 failed, 1 deselected, exit 1). Final held-return, stale sender, nested publication
and existing publication/payload release tests passed together (5 passed,
11.53 seconds, exit 0). The original four lifecycle cases were executed once
after the fix with weak-only instrumentation (4 passed, 18.76 seconds, exit 0;
60-second outer timeout, not reached). Setup failures before collection are
retained: two sandbox dependency reads and duplicate pytest-qt registration.
They are not test passes or executions of the four-case set.

An additional existing mock-only declining-close test initially failed both with
this fix and with the released c8fd closeEvent injected: Mock fabricated a truthy
is_project_save attribute and routed a non-save fixture into the save path.
The fixture now explicitly sets is_project_save=False; its no-cancel/ignored-close
assertions are unchanged. Both failure logs are retained.

The instrumentation holds no strong target references, does not disable/force
GC, records test boundaries, and patches QSettings only in the test process to
use private INI files. It recorded 191 GC start/stop pairs, 28 Python finalizers
and seven native QObject destroys. Every observed finalizer/destroy matched its
construction thread. Eight QObject targets were tracked; one native destroy was
not observed. Four slotted TaskContext instances could not be weak-referenced
and were explicitly reported as such. These observations do not prove a common
historical GC root or that every possible teardown path is safe.

Evidence uses shared FLP Python 3.14.0, NumPy 2.4.1, PySide6/Qt 6.10.1 and temporary
pytest-qt 4.5.0. Complete commands, physical source hashes, failed setup logs,
JSONL events and exit codes accompany the small delivery package. The four-case
test source is unchanged. No full-suite, large replay, hardware qualification,
stable-branch integration or live user-GUI manipulation is claimed.
