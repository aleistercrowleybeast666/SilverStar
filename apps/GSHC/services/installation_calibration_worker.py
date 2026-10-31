"""Single-job GSHC worker; no widgets, serial imports or unbounded job queue."""
from dataclasses import dataclass
from queue import Empty, Full, Queue
from threading import Event, Lock, Thread

from services.installation_calibration_backend import InstallationOutcome, InstallationResult


@dataclass(frozen=True)
class InstallationJob:
    action: str
    arguments: tuple=()


class InstallationWorker:
    def __init__(self,backend):
        self.backend=backend; self._jobs=Queue(1); self._results=Queue(1); self._progress=Queue(32)
        self._stop=Event(); self._cancel=Event(); self._lock=Lock(); self._outstanding=False
        self._thread=None; self.progress_coalesced=0

    def Submit(self,job):
        caps=self.backend.capabilities
        if getattr(job,'action','') in ('apply','save') and (caps is None or not
                (caps.apply_supported if job.action=='apply' else caps.save_supported)):
            return InstallationOutcome(InstallationResult.ApplyDisabled,'TARGET_ACTIVE_CAPABILITY_REQUIRED')
        if not isinstance(job,InstallationJob) or job.action not in ("probe","begin","face","fit","snapshot","replay","export","apply","save","verify_saved","close"):
            return InstallationOutcome(InstallationResult.ApplyDisabled if getattr(job,"action","") in ("apply","save","upload")
                else InstallationResult.Invalid,"JOB_NOT_ALLOWED")
        allowed={"probe":set(),"begin":{"archive_path","imu_instance","mag_instance"},"face":{"face","attempt","stage","mode"},
                 "fit":{"policy"},"snapshot":set(),"replay":{"path"},"export":{"path"},
                 "apply":{"candidate_path"},"save":set(),"verify_saved":{"candidate_path"},"close":set()}
        if (type(job.arguments) is not tuple or len(job.arguments)>8
                or any(type(pair) is not tuple or len(pair)!=2 or pair[0] not in allowed[job.action] for pair in job.arguments)
                or len({pair[0] for pair in job.arguments})!=len(job.arguments)):
            return InstallationOutcome(InstallationResult.Invalid,"BOUNDED_JOB_ARGUMENTS")
        with self._lock:
            if self._stop.is_set() or self._outstanding:
                return InstallationOutcome(InstallationResult.Busy,"ONE_JOB_AND_RESULT_SLOT")
            self._outstanding=True; self._cancel.clear()
            if self._thread is None:
                self._thread=Thread(target=self._run,name="installation-calibration",daemon=False)
                self._thread.start()
            self._jobs.put_nowait(job)
        return InstallationOutcome(InstallationResult.Ok,"QUEUED_NOT_COMPLETE")

    def Cancel(self): self._cancel.set()

    def _emit_progress(self,*args):
        try: self._progress.put_nowait(tuple(args))
        except Full:
            self._progress.get_nowait(); self._progress.put_nowait(tuple(args)); self.progress_coalesced+=1

    def _run(self):
        try:
            while not self._stop.is_set():
                try: job=self._jobs.get(timeout=.05)
                except Empty: continue
                kwargs=dict(job.arguments)
                try:
                    if job.action=="probe": outcome=self.backend.Probe(cancel=self._cancel,progress=self._emit_progress)
                    elif job.action=="begin": outcome=self.backend.Begin(cancel=self._cancel,progress=self._emit_progress,**kwargs)
                    elif job.action=="face": outcome=self.backend.Face(cancel=self._cancel,progress=self._emit_progress,**kwargs)
                    elif job.action=="fit": outcome=self.backend.Fit(cancel=self._cancel,progress=self._emit_progress,**kwargs)
                    elif job.action=="replay": outcome=self.backend.Replay(**kwargs)
                    elif job.action=="export": outcome=self.backend.ExportCandidate(**kwargs)
                    elif job.action=="apply": outcome=self.backend.Apply(cancel=self._cancel,progress=self._emit_progress,**kwargs)
                    elif job.action=="save": outcome=self.backend.Save(cancel=self._cancel,progress=self._emit_progress)
                    elif job.action=="verify_saved": outcome=self.backend.VerifySaved(cancel=self._cancel,progress=self._emit_progress,**kwargs)
                    elif job.action=="snapshot": outcome=InstallationOutcome(InstallationResult.Ok,"CANDIDATE_SNAPSHOT",self.backend.CandidateSnapshot())
                    else: outcome=self.backend.Cleanup()
                except InterruptedError as exc:
                    self.backend.Cleanup(); outcome=InstallationOutcome(InstallationResult.Cancelled,str(exc))
                except TimeoutError as exc:
                    self.backend.Cleanup(); outcome=InstallationOutcome(InstallationResult.Timeout,str(exc))
                except (ValueError,TypeError,KeyError,IndexError,OSError,RuntimeError) as exc:
                    self.backend.Cleanup(); outcome=InstallationOutcome(InstallationResult.Failed,str(exc))
                except Exception as exc:
                    self.backend.Cleanup(); outcome=InstallationOutcome(InstallationResult.Failed,
                        "UNEXPECTED_BACKEND_ERROR:"+type(exc).__name__+":"+str(exc))
                self._results.put_nowait(outcome)
        finally:
            self.backend.Cleanup()

    def TakeResult(self):
        try: result=self._results.get_nowait()
        except Empty: return None
        with self._lock: self._outstanding=False
        return result

    def TakeProgress(self):
        result=[]
        for _ in range(32):
            try: result.append(self._progress.get_nowait())
            except Empty: break
        return tuple(result)

    def Close(self,timeout=7):
        if not 0<timeout<=10: raise ValueError("bounded worker join")
        self._stop.set(); self._cancel.set()
        if self._thread is not None:
            self._thread.join(timeout)
            if self._thread.is_alive(): return InstallationOutcome(InstallationResult.Unknown,"WORKER_CLEANUP_UNCONFIRMED")
        return InstallationOutcome(InstallationResult.Ok if self.backend.cleanup_confirmed else InstallationResult.Unknown,
            "WORKER_STOPPED" if self.backend.cleanup_confirmed else "REMOTE_CLEANUP_UNCONFIRMED")

    def Stop_Request(self):
        """Nonblocking GUI shutdown; ownership is retained until Stopped_Get."""
        self._stop.set(); self._cancel.set()

    def Stopped_Get(self):
        return self._thread is None or not self._thread.is_alive()
