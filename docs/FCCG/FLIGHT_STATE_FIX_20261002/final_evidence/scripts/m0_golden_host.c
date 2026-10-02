#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "air_protocol.h"
#include "test_common.h"

static void Golden_Print(AirBuildResult result, const uint8_t *data, uint8_t length)
{
    TEST_CHECK(result == AIR_BUILD_OK);
    TEST_CHECK(Air_FrameValidate(data, length) == AIR_PARSE_OK);
    for (uint8_t i = 0U; i < length; i++) { printf("%02x", data[i]); }
    printf("\n");
}
int main(void)
{
    uint8_t frame[AIR_MAX_FRAME_LEN]; uint8_t length = 0U;
    AirBuildResult result;
    AirPreflightStatePayload pre = {0x12345678U,{100,-200,300},{-400,500,-600},{32767,0,0,0}};
    AirFlightStatePayload flight = {0x12345678U,{100,-200,300},{-400,500,-600},
        {32767,0,0,0},{1.25f,-2.5f,3.75f},{4.0f,-5.0f,6.0f}};
    AirCapabilityPayload capability = {0U,1U,7U,15U,16U,2000U};
    AirPreflightStatusPayload status = {3U,4U,2U,0x15U,3U,3U,127U,0U};
    AirSensorStatusPayload sensor = {5U,1U,0U,255U,0U,0U,1U};
    const uint8_t command[9] = {0x30U,0x2AU,1U,0xC3U,0x3CU,0x5AU,0xA5U,0U,0U};
    AirCmdPayload parsed;
    result=Air_FlightStateBuild(42U,&flight,frame,sizeof(frame),&length);Golden_Print(result,frame,length);
    result=Air_PreflightStateBuild(42U,&pre,frame,sizeof(frame),&length);Golden_Print(result,frame,length);
    result=Air_CapabilityBuild(42U,&capability,frame,sizeof(frame),&length);Golden_Print(result,frame,length);
    result=Air_PreflightStatusBuild(42U,&status,frame,sizeof(frame),&length);Golden_Print(result,frame,length);
    result=Air_SensorStatusBuild(42U,&sensor,frame,sizeof(frame),&length);Golden_Print(result,frame,length);
    result=Air_StatusBuild(42U,3U,0x12345678U,1U,0U,frame,sizeof(frame),&length);Golden_Print(result,frame,length);
    TEST_CHECK(Air_CmdParse(command,sizeof(command),&parsed)==AIR_PARSE_OK);
    TEST_CHECK(parsed.token==AIR_TOKEN_START_MISSION);
    Golden_Print(AIR_BUILD_OK,command,sizeof(command));
    result=Air_AckBuild(42U,11U,1U,0U,0x12345678U,frame,sizeof(frame),&length);Golden_Print(result,frame,length);
    return Test_Finish("M0_golden");
}
