#ifndef __NAVIGATION_JOURNAL_H
#define __NAVIGATION_JOURNAL_H
#include "navigation_replay.h"
#include "navigation_mag_quality.h"
#define NAVIGATION_JOURNAL_REVISION 2U

/* Version 2 adds quality-evidence operation4; version1 layouts are unchanged.
 * little-endian IEEE754 binary64/binary32, padding-free.
 * No operation is complete without all numbered CRC-bound parts.
 * Logger failure permanently invalidates this epoch's complete-journal claim. */
typedef enum {
    NavigationJournalResult_Ok=0,NavigationJournalResult_InvalidInput=1,
    NavigationJournalResult_StorageUnavailable=2,NavigationJournalResult_InvalidState=3
} NavigationJournalResult;
typedef struct {
    uint8_t buffer[4096];
    uint32_t epoch,operation,failures;
    uint16_t size;
    uint8_t algorithm_id,healthy,active,valid;
} NavigationJournal;
NavigationJournalResult NavigationJournal_Initial(NavigationJournal *journal,const NavigationReplay *replay,
    const int32_t origin_geodetic[3],uint16_t magnetic_physical,uint16_t magnetic_descriptor,uint8_t magnetic_bound);
NavigationJournalResult NavigationJournal_Predict(NavigationJournal *journal,
    const NavigationInputIdentity *imu,uint64_t start_us,uint64_t end_us,
    const double gyro[6],const double force[6],NavigationSessionResult result);
NavigationJournalResult NavigationJournal_Observe(NavigationJournal *journal,uint64_t evaluation_us,
    const NavigationReplayObservation *observation,const NavigationReplayOutcome *outcome);
NavigationJournalResult NavigationJournal_Quality(NavigationJournal *journal,uint64_t evaluation_us,
    const NavigationInputIdentity *identity,uint32_t mode,uint32_t native_clock_trusted,
    NavigationMagQualityResult result,const NavigationMagQualityConfig *config,
    const NavigationMagQualityInput *input,const NavigationMagQualityOutput *output);
NavigationJournalResult NavigationJournal_End(NavigationJournal *journal,uint64_t state_us,uint32_t reason);
#endif
