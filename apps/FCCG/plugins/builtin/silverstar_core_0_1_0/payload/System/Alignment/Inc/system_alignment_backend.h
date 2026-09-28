#ifndef __SYSTEM_ALIGNMENT_BACKEND_H
#define __SYSTEM_ALIGNMENT_BACKEND_H

#include "system_alignment.h"

/* Build-time integration symbols supplied by the selected APP target. */
SystemDeviceResult SystemAlignmentBackend_Reset(void);
SystemDeviceResult SystemAlignmentBackend_PrepareMission(void);
SystemDeviceResult SystemAlignmentBackend_FreezeSources(void);
SystemDeviceResult SystemAlignmentBackend_GuardSampleGet(
    SystemAlignmentGuardSample *sample);
void SystemAlignmentBackend_MissionPreparationAbort(void);
SystemDeviceResult SystemAlignmentBackend_SourceStatusGet(
    SystemAlignmentSourceId source_id,
    SystemAlignmentSourceStatus *status);

#endif /* __SYSTEM_ALIGNMENT_BACKEND_H */
