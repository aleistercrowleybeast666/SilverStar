#ifndef __LOGGER_BUS_H
#define __LOGGER_BUS_H

#include <stdint.h>

#include "sslog_protocol.h"

typedef enum
{
    LOGGER_BUS_RESULT_OK = 0U,
    LOGGER_BUS_RESULT_EMPTY,
    LOGGER_BUS_RESULT_FULL,
    LOGGER_BUS_RESULT_BAD_PARAM,
    LOGGER_BUS_RESULT_BAD_STATE
} LoggerBusResult;

typedef enum
{
    LOGGER_BUS_FINALIZATION_IDLE = 0U,
    LOGGER_BUS_FINALIZATION_ARMED,
    LOGGER_BUS_FINALIZATION_DRAINING,
    LOGGER_BUS_FINALIZATION_FINALIZED
} LoggerBusFinalizationState;

typedef enum
{
    LOGGER_BOOTSTRAP = 0U,
    LOGGER_STREAMING_READY
} LoggerBusStartupState;

/* Internal diagnostics; SSLOG STATS and all wire layouts remain unchanged.
 * Counter deltas over elapsed time give the accepted/attempted production rate. */
typedef struct
{
    uint32_t accepted_count;
    uint32_t dequeued_count;
    uint32_t overflow_count;
    uint32_t bootstrap_suppressed_count;
    uint32_t state_reject_count;
    uint32_t capacity_reject_count;
    LoggerBusStartupState startup_state;
    uint16_t normal_count;
    uint16_t estimator_count;
    uint16_t normal_high_water;
    uint16_t estimator_high_water;
} LoggerBusDiagnostics;

LoggerBusResult LoggerBus_DiagnosticsGet(LoggerBusDiagnostics *diagnostics);
/* LoggerTask alone opens admission after durable bootstrap and an empty queue.
 * Suppressed periodic pushes return OK like policy filtering; they were never
 * admitted, consume no queue slot/sequence and increment only suppression. */
LoggerBusResult LoggerBus_StreamingReady(void);
LoggerBusStartupState LoggerBus_StartupStateGet(void);
LoggerBusResult LoggerBus_Init(void);
void LoggerBus_Reset(void);
LoggerBusResult LoggerBus_EventPush(
    uint64_t timestamp_us, FlightLogEventId event_id,
    uint32_t arg0, uint32_t arg1);
LoggerBusResult LoggerBus_StatsPush(
    uint64_t timestamp_us, const FlightLogStatsRecord *record);
LoggerBusResult LoggerBus_EstimatorPush(
    uint64_t timestamp_us, uint32_t valid_flags,
    const FlightLogEstimatorRecord *record);
LoggerBusResult LoggerBus_SystemConfigPush(uint64_t timestamp_us);
LoggerBusResult LoggerBus_MissionConfigPush(uint64_t timestamp_us);
LoggerBusResult LoggerBus_DecoderProfileDescriptorPush(uint64_t timestamp_us);
LoggerBusResult LoggerBus_PureInsPush(
    uint64_t timestamp_us, uint32_t valid_flags,
    const FlightLogPureInsRecord *record);
LoggerBusResult LoggerBus_Kf6DiagnosticPush(
    uint64_t timestamp_us, uint32_t valid_flags,
    const FlightLogKf6DiagnosticRecord *record);
LoggerBusResult LoggerBus_NavigationQualityPush(
    uint64_t timestamp_us, const FlightLogNavigationQualityRecord *record);
LoggerBusResult LoggerBus_Eskf15BodyInputPush(
    uint64_t timestamp_us, const FlightLogEskf15BodyInputRecord *record);
LoggerBusResult LoggerBus_Eskf15StatePush(
    uint64_t timestamp_us, const FlightLogEskf15StateRecord *record);
LoggerBusResult LoggerBus_Eskf15CovariancePush(
    uint64_t timestamp_us, const FlightLogEskf15CovariancePartRecord *identity,
    const float *covariance_row_major);
LoggerBusResult LoggerBus_Eskf15InitialStatePush(
    uint64_t timestamp_us, const FlightLogEskf15StateRecord *record);
LoggerBusResult LoggerBus_Eskf15MeasurementPush(
    uint64_t timestamp_us, const FlightLogEskf15MeasurementRecord *record);

LoggerBusResult LoggerBus_Kf6FullPPush(
    uint64_t timestamp_us, const FlightLogKf6FullPRecord *record);
LoggerBusResult LoggerBus_PowerPush(
    uint64_t timestamp_us, const FlightLogPowerRecord *record);
LoggerBusResult LoggerBus_HealthPush(
    uint64_t timestamp_us, const FlightLogHealthRecord *record);
LoggerBusResult LoggerBus_TelemetryDiagnosticPush(
    uint64_t timestamp_us,
    const FlightLogTelemetryDiagnosticRecord *record);
LoggerBusResult LoggerBus_InitialStatePush(
    uint64_t timestamp_us, const FlightLogInitialStateRecord *record);
LoggerBusResult LoggerBus_GnssNativePush(
    uint64_t timestamp_us, uint32_t valid_flags,
    const FlightLogGnssNativeRecord *record);
LoggerBusResult LoggerBus_BaroNativePush(
    uint64_t timestamp_us, uint32_t valid_flags,
    const FlightLogBaroNativeRecord *record);
LoggerBusResult LoggerBus_MagNativePush(
    uint64_t timestamp_us, uint32_t valid_flags,
    const FlightLogMagNativeRecord *record);
LoggerBusResult LoggerBus_InertialIncrementPush(
    uint64_t timestamp_us, uint32_t valid_flags,
    const FlightLogInertialIncrementRecord *record);
LoggerBusResult LoggerBus_GnssMeasurementPush(
    uint64_t timestamp_us, uint32_t valid_flags,
    const FlightLogGnssMeasurementRecord *record);
LoggerBusResult LoggerBus_BaroMeasurementPush(
    uint64_t timestamp_us, uint32_t valid_flags,
    const FlightLogBaroMeasurementRecord *record);
LoggerBusResult LoggerBus_ImuCorrectedPush(
    uint64_t timestamp_us, uint32_t valid_flags,
    const FlightLogImuCorrectedRecord *record);
LoggerBusResult LoggerBus_CalibrationResultPush(
    uint64_t timestamp_us,
    const FlightLogCalibrationResultRecord *record);
LoggerBusResult LoggerBus_AlignmentResultPush(
    uint64_t timestamp_us,
    const FlightLogAlignmentResultRecord *record);
LoggerBusResult LoggerBus_FinalizationArm(uint64_t landing_timestamp_us);
LoggerBusFinalizationState LoggerBus_FinalizationProcess(uint64_t now_us);
void LoggerBus_FinalizationComplete(void);
LoggerBusFinalizationState LoggerBus_FinalizationStateGet(void);
LoggerBusResult LoggerBus_Pop(FlightLogRecord *record);
LoggerBusResult LoggerBus_EstimatorPop(FlightLogRecord *record);
LoggerBusResult LoggerBus_NextPop(FlightLogRecord *record);
uint16_t LoggerBus_Count(void);
uint32_t LoggerBus_OverflowCountGet(void);

LoggerBusResult LoggerBus_EstimatorStepPush(
    uint64_t timestamp_us, const FlightLogEstimatorStepRecord *record);

LoggerBusResult LoggerBus_NavigationSnapshotPush(uint64_t timestamp_us,
    const FlightLogEstimatorRecord *state, const FlightLogKf6FullPRecord *covariance);

LoggerBusResult LoggerBus_GnssRecoveryPush(
    uint64_t timestamp_us, const FlightLogGnssRecoveryRecord *record);

LoggerBusResult LoggerBus_LandingDiagnosticPush(
    uint64_t timestamp_us, const FlightLogLandingDiagnosticRecord *record);

#endif /* __LOGGER_BUS_H */
