AirBuildResult Air_FlightStateBuild(uint8_t seq,
                                    const AirFlightStatePayload *state,
                                    uint8_t *out_frame,
                                    uint8_t out_size,
                                    uint8_t *out_len)
{
    uint8_t index;

    if ((state == NULL) || (out_frame == NULL) || (out_len == NULL))
    {
        return AIR_BUILD_BAD_PARAM;
    }
    SILVERSTAR_ASSERT_OBJECT(state, AirFlightStatePayload,
        SILVERSTAR_ASSERT_MODULE_PROTOCOL);
    if (out_size < AIR_FLIGHT_STATE_LEN)
    {
        *out_len = 0U;
        return AIR_BUILD_BAD_LEN;
    }
    Air_StatePrefixPut(AIR_TYPE_FLIGHT_STATE, seq, state->time_ms,
                       state->accel_i16, state->gyro_i16,
                       state->quaternion_q15, out_frame);
    for (index = 0U; index < 3U; index++)
    {
        Air_PutFloatLe(&out_frame[26U + ((uint16_t)index * 4U)],
                       state->velocity_enu_mps[index]);
        Air_PutFloatLe(&out_frame[38U + ((uint16_t)index * 4U)],
                       state->position_enu_m[index]);
    }
    *out_len = AIR_FLIGHT_STATE_LEN;
    return AIR_BUILD_OK;
}
