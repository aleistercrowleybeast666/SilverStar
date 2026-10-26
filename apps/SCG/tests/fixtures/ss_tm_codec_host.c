#include "ss_tm_protocol.h"
#include "silverstar_assert.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>

void SilverStarAssert_Check(uint8_t condition, SilverStarAssertModuleId module,
    const char *file, uint32_t line, SilverStarAssertReasonId reason)
{ (void)module; (void)file; (void)line; (void)reason; assert(condition != 0U); }
void SilverStarAssert_ObjectCheck(const volatile void *object, uint32_t alignment,
    SilverStarAssertModuleId module, const char *file, uint32_t line)
{ (void)module; (void)file; (void)line; assert(object != NULL); assert(alignment != 0U); }

static void Test_Print(const uint8_t *data, uint8_t length)
{
    uint8_t index;
    for (index = 0U; index < length; index++) { (void)printf("%02x", data[index]); }
    (void)printf("\n");
}

int main(void)
{
    uint8_t profile;
    for (profile = 0U; profile < 2U; profile++)
    {
        uint8_t frame[AIR_MAX_FRAME_LEN];
        uint8_t length = 0U;
        SsTmEvent event = {0x10203040UL, 123456789ULL, 0x100U, 0x11223344UL, 2U, 65534U, 7U, 9U};
        assert(SsTm_SessionSet(profile, 0x12345678UL) == SS_TM_SESSION_OK);
        SsTm_TimeSet(123456789ULL);
        assert(SsTm_PositionBuild(0, 1799999999L, -12000, 12345U, 65534U, 15U, 12U,
            frame, sizeof(frame), &length) == AIR_BUILD_OK);
        assert(length == 28U && Air_FrameValidate(frame, length) == AIR_PARSE_OK);
        Test_Print(frame, length);
        assert(SsTm_HealthBuild(0U, 65534U, 0x7FFU, 0x42U, frame, sizeof(frame), &length) == AIR_BUILD_OK);
        assert(length == 16U && Air_FrameValidate(frame, length) == AIR_PARSE_OK);
        Test_Print(frame, length);
        assert(Air_AckBuild(0U, 0xBEEFU, AIR_CMD_START_MISSION, AIR_ACK_RESULT_OK, 123456U,
            frame, sizeof(frame), &length) == AIR_BUILD_OK);
        assert(Air_FrameValidate(frame, length) == AIR_PARSE_OK);
        Test_Print(frame, length);
        assert(SsTm_EventBuild(&event, frame, sizeof(frame), &length) == AIR_BUILD_OK);
        assert(Air_FrameValidate(frame, length) == AIR_PARSE_OK);
        Test_Print(frame, length);
        frame[0] = 2U; assert(Air_FrameValidate(frame, length) != AIR_PARSE_OK);
        frame[0] = 1U; frame[1] ^= 0x80U; assert(Air_FrameValidate(frame, length) != AIR_PARSE_OK);
        assert(SsTm_HealthBuild(4000U, 0U, 0U, 1U, frame, sizeof(frame), &length) != AIR_BUILD_OK);
        assert(SsTm_PositionBuild(900000001L, 0, 0, 0U, 0U, 3U, 0U,
            frame, sizeof(frame), &length) != AIR_BUILD_OK);
    }
    return EXIT_SUCCESS;
}
