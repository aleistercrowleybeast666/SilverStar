static uint32_t Lora_PacketAirtimeMs(uint8_t instance, uint8_t length)
{
    uint32_t bandwidth = 0U;
    uint32_t sf = (uint32_t)s_mod_params.Params.LoRa.SpreadingFactor >> 4U;
    uint32_t cr = (uint32_t)s_mod_params.Params.LoRa.CodingRate;
    uint32_t preamble = (uint32_t)(s_pkt_params.Params.LoRa.PreambleLength & 0x0FU) <<
        ((uint32_t)s_pkt_params.Params.LoRa.PreambleLength >> 4U);
    SILVERSTAR_ASSERT((sf >= 5U) && (sf <= 12U) &&
        ((uint32_t)s_mod_params.Params.LoRa.SpreadingFactor == (sf << 4U)) &&
        (cr >= 1U) && (cr <= 4U),
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    SILVERSTAR_ASSERT((s_mod_params.PacketType == PACKET_TYPE_LORA) &&
        (s_pkt_params.PacketType == PACKET_TYPE_LORA) &&
        ((s_pkt_params.Params.LoRa.HeaderType == LORA_PACKET_VARIABLE_LENGTH) ||
         (s_pkt_params.Params.LoRa.HeaderType == LORA_PACKET_FIXED_LENGTH)) &&
        ((s_pkt_params.Params.LoRa.CrcMode == LORA_CRC_ON) || (s_pkt_params.Params.LoRa.CrcMode == LORA_CRC_OFF)) &&
        (preamble == LORA_CFG_PREAMBLE_SYMBOLS),
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    SILVERSTAR_ASSERT((length > 0U) && (length <= LORA_MAX_PAYLOAD_LEN),
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_LENGTH_RANGE);
    switch (s_mod_params.Params.LoRa.Bandwidth)
    {
        case LORA_BW_0200: bandwidth = 203125U; break;
        case LORA_BW_0400: bandwidth = 406250U; break;
        case LORA_BW_0800: bandwidth = 812500U; break;
        case LORA_BW_1600: bandwidth = 1625000U; break;
        default: break;
    }
    SILVERSTAR_ASSERT(bandwidth != 0U,
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    int32_t bits = (int32_t)(8U * length) - (int32_t)(4U * sf);
    if (s_pkt_params.Params.LoRa.CrcMode == LORA_CRC_ON) { bits += 16; }
    if (s_pkt_params.Params.LoRa.HeaderType == LORA_PACKET_VARIABLE_LENGTH) { bits += 20; }
    if (sf >= 7U) { bits += 8; }
    uint32_t denominator = 4U * ((sf > 10U) ? (sf - 2U) : sf);
    uint32_t blocks = (bits > 0) ? ((uint32_t)bits + denominator - 1U) / denominator : 0U;
    uint32_t quarter_symbols = 4U * (preamble + 8U + blocks * (cr + 4U)) +
        ((sf < 7U) ? 25U : 17U);
    uint64_t numerator = (uint64_t)quarter_symbols * (1UL << sf) * 1000ULL;
    return (uint32_t)((numerator + (uint64_t)4U * bandwidth - 1U) / ((uint64_t)4U * bandwidth));
}
