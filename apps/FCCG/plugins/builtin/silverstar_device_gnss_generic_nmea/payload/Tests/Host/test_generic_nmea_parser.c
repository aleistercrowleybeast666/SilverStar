#include "generic_nmea_parser.h"

#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

static void TestNmea_Send(GenericNmeaParser *parser, const char *body,
    uint64_t receive_us)
{
    char sentence[GENERIC_NMEA_MAX_SENTENCE + 8U];
    uint8_t checksum = 0U;
    size_t index;
    int length;
    for (index = 0U; body[index] != '\0'; index++)
    { checksum ^= (uint8_t)body[index]; }
    length = snprintf(sentence, sizeof(sentence), "$%s*%02X\r\n", body,
        (unsigned int)checksum);
    assert(length > 0 && (size_t)length < sizeof(sentence));
    assert(GenericNmeaParser_Feed(parser, (const uint8_t *)sentence,
        (uint16_t)length, receive_us) == GenericNmeaFeedOk);
}

static void TestNmea_CompleteEpoch(void)
{
    GenericNmeaParser parser;
    GenericNmeaParser_Init(&parser);
    TestNmea_Send(&parser,
        "GPGGA,123519.00,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,",
        1000000U);
    TestNmea_Send(&parser,
        "GPRMC,123519.00,A,4807.038,N,01131.000,E,022.4,084.4,230394,,,A",
        1000100U);
    TestNmea_Send(&parser,
        "GPGST,123519.00,1.0,1.0,1.0,0.0,0.6,0.8,1.2",
        1000200U);
    assert(parser.has_published == 0U);
    TestNmea_Send(&parser,
        "GNGGA,123520.00,4807.039,N,01131.001,E,1,08,0.9,545.5,M,46.9,M,,",
        2000000U);
    assert(parser.has_published != 0U && parser.published.sequence == 1U);
    assert(parser.published.latitude_e7 > 481172000);
    assert(parser.published.msl_height_mm == 545400);
    assert((parser.published.valid_fields & SYSTEM_GNSS_FIELD_VELOCITY_HORIZONTAL) != 0U);
    assert((parser.published.valid_fields & SYSTEM_GNSS_FIELD_HORIZONTAL_ACCURACY) != 0U);
    assert((parser.published.valid_fields & SYSTEM_GNSS_FIELD_VELOCITY_VERTICAL) == 0U);
    assert(fabsf(parser.published.velocity_enu_mps[0] - 11.4F) < 0.5F);
    TestNmea_Send(&parser,
        "GNGGA,123521.00,4807.040,N,01131.002,E,1,08,0.9,545.6,M,46.9,M,,",
        3000000U);
    assert(parser.published.sequence == 2U);
    assert((parser.published.valid_fields & SYSTEM_GNSS_FIELD_VELOCITY_HORIZONTAL) == 0U);
    assert((parser.published.valid_fields & SYSTEM_GNSS_FIELD_HORIZONTAL_ACCURACY) == 0U);
}

static void TestNmea_IntegrityBounds(void)
{
    GenericNmeaParser parser;
    uint8_t excessive[GENERIC_NMEA_MAX_BYTES_PER_PROCESS + 1U] = {0};
    uint8_t overlength[GENERIC_NMEA_MAX_SENTENCE + 8U];
    const uint8_t invalid[] = "$GPRMC,123519,A,,,,,,*00\r\n";
    GenericNmeaParser_Init(&parser);
    assert(GenericNmeaParser_Feed(&parser, invalid,
        (uint16_t)(sizeof(invalid) - 1U), 1000U) == GenericNmeaFeedOk);
    assert(parser.checksum_errors == 1U && parser.sequence == 0U);
    assert(GenericNmeaParser_Feed(&parser, excessive, sizeof(excessive), 1000U) ==
        GenericNmeaFeedLimitExceeded);
    (void)memset(overlength, 'A', sizeof(overlength));
    overlength[0] = '$';
    overlength[sizeof(overlength) - 1U] = '\n';
    assert(GenericNmeaParser_Feed(&parser, overlength,
        sizeof(overlength), 1500U) == GenericNmeaFeedOk);
    assert(parser.overlength_sentences == 1U);
    TestNmea_Send(&parser,
        "GNRMC,123519.00,A,4807.038,N,01131.000,E,1.0,0.0,230394,,,A",
        2000U);
    TestNmea_Send(&parser,
        "GNRMC,123520.00,A,4807.038,N,01131.000,E,1.0,0.0,230394,,,A",
        3000U);
    assert(parser.sequence == 1U);
    assert(parser.published.fix_type == 2U);
    assert((parser.published.valid_fields & SYSTEM_GNSS_FIELD_HEIGHT) == 0U);
}

static void TestNmea_GnsAndVtg(void)
{
    GenericNmeaParser parser;
    GenericNmeaParser_Init(&parser);
    TestNmea_Send(&parser,
        "GNGNS,082310.00,4807.038,N,01131.000,E,AN,10,1.0,500.0,40.0,,",
        1000000U);
    TestNmea_Send(&parser, "GNVTG,90.0,T,,M,10.0,N,18.5,K,A", 1000100U);
    TestNmea_Send(&parser,
        "GNRMC,082311.00,A,4807.040,N,01131.002,E,10.0,90.0,230394,,,A",
        2000000U);
    assert(parser.sequence == 1U);
    assert(parser.published.msl_height_mm == 500000);
    assert(parser.published.satellite_count == 10U);
    assert((parser.published.valid_fields & SYSTEM_GNSS_FIELD_VELOCITY_HORIZONTAL) != 0U);
    assert(fabsf(parser.published.velocity_enu_mps[0] - 5.144444F) < 0.05F);
    assert((parser.published.valid_fields & SYSTEM_GNSS_FIELD_VELOCITY_VERTICAL) == 0U);
}

static void TestNmea_StaleUntimedVtgIgnored(void)
{
    GenericNmeaParser parser;
    GenericNmeaParser_Init(&parser);
    TestNmea_Send(&parser,
        "GNGGA,082310.00,4807.038,N,01131.000,E,1,08,0.9,500.0,M,40.0,M,,",
        1000000U);
    TestNmea_Send(&parser, "GNVTG,90.0,T,,M,10.0,N,18.5,K,A", 3000000U);
    TestNmea_Send(&parser,
        "GNGGA,082311.00,4807.039,N,01131.001,E,1,08,0.9,500.1,M,40.0,M,,",
        3100000U);
    assert(parser.sequence == 1U);
    assert((parser.published.valid_fields & SYSTEM_GNSS_FIELD_VELOCITY_HORIZONTAL) == 0U);
}

int main(void)
{
    TestNmea_CompleteEpoch();
    TestNmea_IntegrityBounds();
    TestNmea_GnsAndVtg();
    TestNmea_StaleUntimedVtgIgnored();
    return 0;
}
