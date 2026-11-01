"""Read-only target admission, aggregated from the existing domain validators.

This is configuration readiness to request generation, not generated-artifact,
toolchain, hardware, runtime READY or flight qualification evidence.
"""
from dataclasses import dataclass

from silverstar_fccg.project.air_link import AirLinkIssue, GroundTargetIssues_Get
from silverstar_fccg.project.radio_transaction import RadioTransaction_IssuesGet
from silverstar_fccg.project.validation import Project_Validate


@dataclass(frozen=True, slots=True)
class TargetReadiness:
    target: str
    issues: tuple

    @property
    def ready(self) -> bool:
        return not self.issues


def TargetReadiness_Get(model, catalog, target: str) -> TargetReadiness:
    """A missing peer may be omitted; an explicitly configured conflict may not."""
    if target not in ('flight', 'ground'):
        raise ValueError('Unknown generation target')
    issues = list(RadioTransaction_IssuesGet(model, catalog))
    if target == 'flight':
        issues.extend(issue for issue in Project_Validate(model, catalog).issues
                      if issue.level == 'error')
        hardware = model.hardware
    else:
        issues.extend(GroundTargetIssues_Get(model, catalog))
        hardware = model.ground_target.hardware
    if hardware.mode == 'unselected' or (hardware.mode == 'custom' and not hardware.snapshot_id):
        issues.insert(0, AirLinkIssue('TARGET_HARDWARE_UNBOUND',
                                    'Select a PCB or import the complete CubeMX project.'))
    # Preserve the canonical issues without depending on different issue classes
    # having the same dataclass equality semantics.
    unique = {(issue.code, issue.message): issue for issue in issues}
    return TargetReadiness(target, tuple(unique.values()))
