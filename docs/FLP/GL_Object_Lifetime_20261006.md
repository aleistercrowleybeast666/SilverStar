# GL QObject lifetime repair (2026-10-06)

Scope: isolated FLP lifecycle delta on `8de4d08b97e6267e1a699b514258c85d7251909a`. The stable `cd76d8e` checkout remains unchanged. Integration requires independent review. This repair addresses a reproduced native QObject destruction hazard; the two cloud combination crashes remain unattributed.

## Ownership contract

pyqtgraph 0.14.0 GLViewMixin creates an unparented `keyTimer`. It holds scene items in a Python list; each item also references its view. `GLGraphicsItem.setParentItem` manages Python scenegraph relationships, separate from QObject parent ownership. `GLGridItem` has an internal lineplot child through that scenegraph. Destroying the native GUI window can leave those Python-owned, GUI-affine QObjects in reference cycles for later collection by a worker.

The existing CameraLockGLViewWidget now parents `keyTimer` to itself and, when adding an item, adopts its existing scenegraph descendants into a matching QObject tree. All fixed first-party chart items are created before being added. No scenegraph `parentItem`, data, transforms, layout, visibility, camera behavior, algorithm or cache contract is changed. The other numerical identity inputs, original 17 progress/lifecycle tests and worker protocol are unchanged.

QObject removal is deliberately not inferred from scene removal: inherited `removeItem` and `clear` remain nondestructive, while removed objects retain their last view's QObject ownership until re-added to another view or destroyed with the owner. This can retain cleared objects until view destruction; current charts initialize a fixed scene and subsequently update data/visibility. Moving an object to another view is tested with remove/clear followed by add on the GUI thread. Direct later scenegraph reparenting or adding children after adoption does not automatically synchronize QObject ownership and is outside this repair's supported scope. This is not a generic dynamic-scene reclamation mechanism.

Qt parent-driven native deletion invalidates the wrappers; later Python collection must not delete the native object again. The regression records GUI affinity, C++ ownership, non-null QObject parent, and exactly one native destruction per tracked item, including grid children and timers. This change does not manage all OpenGL value objects, GPU allocations or context teardown paths.

Qt's [Threads and QObjects](https://doc.qt.io/qt-6/threads-qobject.html) and [QObject destructor documentation](https://doc.qt.io/qt-6/qobject.html#dtor.QObject) describe owner-thread destruction and deferred deletion. [Shiboken ownership documentation](https://doc.qt.io/qtforpython-6/shiboken6/typesystem_ownership.html) describes native versus wrapper ownership. The local installed dependency source, version and license were included in the prior diagnostic package.

## Pre-fix and post-fix evidence

The earlier persisted diagnosis on unchanged 8de produced **31 → 2 → 0** wrong-thread native destructions: baseline, incomplete top-level-only test proposal, complete proposal including grid children. GC stayed enabled and still collected 497 objects. Its initial close-only probe exited 0 but produced approximately 3.46 MB of closed-writer errors during shutdown; it is not a clean pass. Original cloud crash logs were lost on cloud workspace replacement; the retained handoff is a summary, not reconstructed raw logs.

The committed regression uses three independent short processes with empty offscreen GUIs and explicit worker GC, without numerical runs or source logs:

- Before product repair: **3 failed**, exit 1 (`pre.txt`). MainWindow reports 31 wrong-thread native destructions; transfer and multiple-window cases fail their ownership/deletion contracts.
- Initial post-fix: **3 passed**, exit 0 (`post.txt`). A read-only per-object trace audit also confirms all 31/6/6 monitored objects are Qt-owned, GUI-affine and each destroyed exactly once on GUI.
- Final post-fix, with additional explicit per-object assertions: **3 passed**, exit 0 (`final-lifetime.txt`). The original assertions and probe body remain unchanged; the outer test now also requires Qt ownership and each tracked native destruction exactly once. The package preserves the pre-addition outer-test snapshot and clearly distinguishes its pre/intermediate scope.

All actual outcomes, source snapshots/hashes, raw subprocess traces, stdout/stderr, exit codes, commands and warnings are retained in `.work/evidence/gl-owner-fix-20261006` and its review package. Offscreen warnings about unsupported QOpenGLWidget and missing bundled Qt font directory are preserved, not suppressed.

The authorized original 17-case progress/storage/GUI combination was executed once after this repair: **17 passed in 90.01s**, exit 0 (`combined17.txt`). Original test files and expected behavior are unchanged. A separate observer records GC activity/enabled state and existing pytest-qt messages without replacing message capture, changing test outcomes or retaining QObjects. It records 792 GC start/stop events across six threads, with GC enabled at all recorded phases.

The complete Qt receipt contains 59 messages: 24 offscreen QOpenGLWidget warnings, one missing bundled font-directory warning, and **34 `QBasicTimer::start: Timers cannot be started from another thread` warnings** during the corrupt-cache open case. They are not ignored, suppressed or converted to passes. The recorder's thread field for Qt messages is the GUI reporting/harvesting thread, not the original emitter thread; the warning's native caller and involved object remain unknown. Thus the passing assertions do not establish clean GUI thread behavior or complete acceptance. This unresolved warning and the cloud crash attribution continue to block a complete lifecycle/GUI acceptance claim. The combination was not repeated to seek a cleaner result.

## Limited actual rendering smoke

One new private, nonmodal Windows window without log/decoder data was shown without requesting activation and then closed. It contained a grid, line, text and triangle mesh. A valid OpenGL context and a 623 × 398 framebuffer were observed; the captured PNG is 20,261 bytes, SHA256 `5556699fee11efc6d24155c135670d765305083b8e6a3558d2527f1629a0fb0a`. Renderer: Intel(R) UHD Graphics; GL 4.6.0, build 31.0.101.1999. All six tracked QObjects were destroyed once on the GUI thread, GC remained enabled, process exit 0, and no Qt messages were recorded. The helper closed only its own window. No existing user software was closed or controlled.

That smoke proves only its recorded display/framebuffer/close path. Actual rendering resource destruction across all charts, multiple GL contexts, graphics backends/drivers, long sessions and the cloud failures remain **NOT PROVEN**. No full hardware, whole-FLP or broad GUI acceptance is claimed. No firmware, GSHC, SCG, SF6 math, cache identity, parser or persistence safety change is included.
