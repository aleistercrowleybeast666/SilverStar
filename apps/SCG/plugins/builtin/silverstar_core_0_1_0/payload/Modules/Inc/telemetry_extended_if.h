#ifndef __TELEMETRY_EXTENDED_IF_H
#define __TELEMETRY_EXTENDED_IF_H
/* Extended wire operations. Include after the selected payload type contract.
 * Only the SS-TM profile links these operations; M0 never calls them. */
typedef struct
{
    uint32_t event_id;
    uint64_t occurred_us;
    uint16_t event_code;
    uint32_t stage_id;
    uint16_t instance_id;
    uint16_t transaction_id;
    uint8_t arg0;
    uint8_t arg1;
} SsTmEvent;

typedef enum { SS_TM_SESSION_OK = 0, SS_TM_SESSION_INVALID } SsTmSessionResult;
SsTmSessionResult SsTm_SessionSet(uint8_t profile, uint32_t boot_session);
void SsTm_TimeSet(uint64_t monotonic_us);
uint16_t SsTm_FrameSequenceGet(const uint8_t *frame);
uint8_t SsTm_FrameTypeGet(const uint8_t *frame);
uint32_t SsTm_EventIdNext(void);
AirBuildResult SsTm_EventBuild(const SsTmEvent *event, uint8_t *out, uint8_t capacity, uint8_t *length);
AirBuildResult SsTm_PositionBuild(int32_t latitude, int32_t longitude, int32_t height, uint32_t age_ms, uint16_t accuracy_cm, uint8_t flags, uint8_t satellites, uint8_t *out, uint8_t capacity, uint8_t *length);
AirBuildResult SsTm_HealthBuild(uint16_t battery_mv, uint16_t age_ds, uint16_t known, uint16_t fault, uint8_t *out, uint8_t capacity, uint8_t *length);
AirBuildResult SsTm_SequenceRefresh(uint8_t *frame, uint8_t length);


#endif /* __TELEMETRY_EXTENDED_IF_H */
