#include "generic_nmea_parser.h"

#include <math.h>
#include <stddef.h>
#include <string.h>

#define GENERIC_NMEA_MAX_FIELDS 24U
#define GENERIC_NMEA_KNOT_MPS 0.514444444F
#define GENERIC_NMEA_PI_DIV_180 0.01745329252F
#define GENERIC_NMEA_AUX_MAX_LAG_US 1000000ULL

static int8_t GenericNmeaParser_HexDigit(char value)
{
    if ((value >= '0') && (value <= '9')) { return (int8_t)(value - '0'); }
    if ((value >= 'A') && (value <= 'F')) { return (int8_t)(value - 'A' + 10); }
    if ((value >= 'a') && (value <= 'f')) { return (int8_t)(value - 'a' + 10); }
    return -1;
}

static uint8_t GenericNmeaParser_DecimalGet(const char *text, float *value)
{
    uint32_t integer = 0U;
    uint32_t fraction = 0U;
    uint32_t divisor = 1U;
    uint8_t digits = 0U;
    uint8_t negative = 0U;
    uint8_t index = 0U;
    if ((text == NULL) || (value == NULL)) { return 0U; }
    if (text[0] == '-') { negative = 1U; index = 1U; }
    for (; (text[index] >= '0') && (text[index] <= '9') && (index < 20U); index++)
    {
        if (integer > 100000000U) { return 0U; }
        integer = integer * 10U + (uint32_t)(text[index] - '0');
        digits++;
    }
    if (text[index] == '.')
    {
        index++;
        for (; (text[index] >= '0') && (text[index] <= '9') && (index < 20U); index++)
        {
            if (divisor >= 1000000U) { return 0U; }
            fraction = fraction * 10U + (uint32_t)(text[index] - '0');
            divisor *= 10U;
            digits++;
        }
    }
    if ((digits == 0U) || (text[index] != '\0')) { return 0U; }
    *value = (float)integer + (float)fraction / (float)divisor;
    if (negative != 0U) { *value = -*value; }
    return isfinite(*value) ? 1U : 0U;
}

static uint8_t GenericNmeaParser_UtcGet(const char *text, uint32_t *epoch)
{
    uint32_t value = 0U;
    uint32_t milliseconds = 0U;
    uint8_t index;
    uint8_t count = 0U;
    if ((text == NULL) || (epoch == NULL) || (strlen(text) < 6U) ||
        (strlen(text) > 12U)) { return 0U; }
    for (index = 0U; index < 6U; index++)
    {
        if ((text[index] < '0') || (text[index] > '9')) { return 0U; }
        value = value * 10U + (uint32_t)(text[index] - '0');
    }
    if (((value / 10000U) > 23U) || (((value / 100U) % 100U) > 59U) ||
        ((value % 100U) > 60U)) { return 0U; }
    if (text[6] == '.')
    {
        for (index = 7U; (text[index] >= '0') && (text[index] <= '9') &&
             (index < 13U); index++)
        {
            if (count < 3U)
            {
                milliseconds = milliseconds * 10U +
                    (uint32_t)(text[index] - '0');
                count++;
            }
        }
        if (text[index] != '\0') { return 0U; }
        while (count < 3U) { milliseconds *= 10U; count++; }
    }
    else if (text[6] != '\0') { return 0U; }
    *epoch = (((value / 10000U) * 3600U) +
        (((value / 100U) % 100U) * 60U) + (value % 100U)) * 1000U +
        milliseconds;
    return 1U;
}

static uint8_t GenericNmeaParser_CoordinateGet(const char *text,
    const char *hemisphere, uint8_t latitude, int32_t *value_e7)
{
    float raw;
    uint32_t degrees;
    float decimal;
    if ((GenericNmeaParser_DecimalGet(text, &raw) == 0U) ||
        (raw < 0.0F) || (hemisphere == NULL) ||
        (hemisphere[0] == '\0') || (hemisphere[1] != '\0')) { return 0U; }
    degrees = (uint32_t)(raw / 100.0F);
    decimal = (float)degrees + (raw - (float)degrees * 100.0F) / 60.0F;
    if ((raw - (float)degrees * 100.0F >= 60.0F) ||
        (decimal > (latitude != 0U ? 90.0F : 180.0F))) { return 0U; }
    if ((latitude != 0U && hemisphere[0] != 'N' && hemisphere[0] != 'S') ||
        (latitude == 0U && hemisphere[0] != 'E' && hemisphere[0] != 'W'))
    { return 0U; }
    if ((hemisphere[0] == 'S') || (hemisphere[0] == 'W')) { decimal = -decimal; }
    *value_e7 = (int32_t)roundf(decimal * 10000000.0F);
    return 1U;
}

static void GenericNmeaParser_PositionSet(GenericNmeaParser *parser,
    const char *lat, const char *ns, const char *lon, const char *ew)
{
    int32_t latitude;
    int32_t longitude;
    if ((GenericNmeaParser_CoordinateGet(lat, ns, 1U, &latitude) != 0U) &&
        (GenericNmeaParser_CoordinateGet(lon, ew, 0U, &longitude) != 0U))
    {
        parser->pending.latitude_e7 = latitude;
        parser->pending.longitude_e7 = longitude;
        parser->valid_fields |= SYSTEM_GNSS_FIELD_POSITION;
    }
}

static void GenericNmeaParser_VelocitySet(GenericNmeaParser *parser,
    const char *course_text, const char *speed_text)
{
    float course;
    float knots;
    float radians;
    if ((GenericNmeaParser_DecimalGet(course_text, &course) == 0U) ||
        (GenericNmeaParser_DecimalGet(speed_text, &knots) == 0U) ||
        (course < 0.0F) || (course >= 360.0F) ||
        (knots < 0.0F) || (knots > 10000.0F)) { return; }
    radians = course * GENERIC_NMEA_PI_DIV_180;
    parser->pending.velocity_enu_mps[0] = sinf(radians) * knots * GENERIC_NMEA_KNOT_MPS;
    parser->pending.velocity_enu_mps[1] = cosf(radians) * knots * GENERIC_NMEA_KNOT_MPS;
    parser->valid_fields |= SYSTEM_GNSS_FIELD_VELOCITY_HORIZONTAL;
}

static void GenericNmeaParser_EpochBegin(GenericNmeaParser *parser,
    uint32_t epoch, uint64_t receive_us)
{
    if ((parser->has_epoch != 0U) && (parser->epoch != epoch) &&
        ((parser->valid_fields & SYSTEM_GNSS_FIELD_POSITION) != 0U))
    {
        parser->published = parser->pending;
        parser->published.valid_fields = parser->valid_fields;
        /* Absence of GST or a vertical velocity sentence is a capability gap,
         * never a synthetic zero-valued measurement. */
        parser->published.supported_fields = parser->valid_fields;
        parser->published.sequence = ++parser->sequence;
        parser->published.receive_timestamp_us = parser->last_receive_us;
        parser->published.sample_timestamp_us = parser->last_receive_us;
        parser->has_published = 1U;
    }
    if ((parser->has_epoch == 0U) || (parser->epoch != epoch))
    {
        (void)memset(&parser->pending, 0, sizeof(parser->pending));
        parser->valid_fields = 0U;
        parser->epoch = epoch;
        parser->has_epoch = 1U;
    }
    parser->last_receive_us = receive_us;
}

static void GenericNmeaParser_FixSet(GenericNmeaParser *parser,
    uint8_t fix_valid, uint8_t has_vertical_fix)
{
    parser->pending.fix_ok = fix_valid;
    parser->pending.fix_type = fix_valid != 0U ?
        (has_vertical_fix != 0U ? 3U : 2U) : 0U;
    parser->valid_fields |= SYSTEM_GNSS_FIELD_FIX_TYPE | SYSTEM_GNSS_FIELD_FIX_OK;
}

static void GenericNmeaParser_SentenceApply(GenericNmeaParser *parser,
    char *body, uint64_t receive_us)
{
    char *fields[GENERIC_NMEA_MAX_FIELDS] = {0};
    uint8_t count = 1U;
    uint8_t index;
    uint8_t body_length = (uint8_t)strlen(body);
    uint32_t epoch;
    float value;
    fields[0] = body;
    for (index = 0U; index < body_length; index++)
    {
        if (body[index] == ',' && count < GENERIC_NMEA_MAX_FIELDS)
        { body[index] = '\0'; fields[count++] = &body[index + 1U]; }
    }
    if ((strlen(fields[0]) != 5U) ||
        (fields[0][0] < 'A') || (fields[0][0] > 'Z') ||
        (fields[0][1] < 'A') || (fields[0][1] > 'Z')) { return; }
    if (((strcmp(&fields[0][2], "GGA") == 0) && (count >= 10U)) ||
        ((strcmp(&fields[0][2], "GNS") == 0) && (count >= 10U)))
    {
        uint8_t gga = (uint8_t)(fields[0][2] == 'G' && fields[0][3] == 'G');
        uint8_t quality_index = 6U;
        uint8_t satellite_index = 7U;
        uint8_t altitude_index = 9U;
        uint8_t geoid_index = gga != 0U ? 11U : 10U;
        uint8_t fix_valid = gga != 0U ?
            (uint8_t)(fields[quality_index][0] == '1' ||
                      fields[quality_index][0] == '2' ||
                      fields[quality_index][0] == '4' ||
                      fields[quality_index][0] == '5') :
            (uint8_t)(strchr(fields[quality_index], 'A') != NULL ||
                      strchr(fields[quality_index], 'D') != NULL ||
                      strchr(fields[quality_index], 'R') != NULL ||
                      strchr(fields[quality_index], 'F') != NULL);
        if (GenericNmeaParser_UtcGet(fields[1], &epoch) == 0U) { return; }
        GenericNmeaParser_EpochBegin(parser, epoch, receive_us);
        GenericNmeaParser_FixSet(parser, fix_valid,
            (uint8_t)(GenericNmeaParser_DecimalGet(fields[altitude_index],
                &value) != 0U && fabsf(value) <= 20000.0F));
        if (fix_valid == 0U) { return; }
        GenericNmeaParser_PositionSet(parser, fields[2], fields[3], fields[4], fields[5]);
        if ((GenericNmeaParser_DecimalGet(fields[satellite_index], &value) != 0U) &&
            (value <= 99.0F))
        { parser->pending.satellite_count = (uint8_t)value;
          parser->valid_fields |= SYSTEM_GNSS_FIELD_SATELLITE_COUNT; }
        if ((GenericNmeaParser_DecimalGet(fields[altitude_index], &value) != 0U) &&
            (fabsf(value) <= 20000.0F))
        {
            parser->pending.msl_height_mm = (int32_t)roundf(value * 1000.0F);
            parser->valid_fields |= SYSTEM_GNSS_FIELD_HEIGHT;
            if ((geoid_index < count) &&
                (GenericNmeaParser_DecimalGet(fields[geoid_index], &value) != 0U) &&
                (fabsf(value) <= 1000.0F))
            { parser->pending.ellipsoid_height_mm = parser->pending.msl_height_mm +
                (int32_t)roundf(value * 1000.0F); }
        }
    }
    else if ((strcmp(&fields[0][2], "RMC") == 0) && (count >= 9U))
    {
        if (GenericNmeaParser_UtcGet(fields[1], &epoch) == 0U) { return; }
        GenericNmeaParser_EpochBegin(parser, epoch, receive_us);
        GenericNmeaParser_FixSet(parser, (uint8_t)(fields[2][0] == 'A'),
            (uint8_t)((parser->valid_fields & SYSTEM_GNSS_FIELD_HEIGHT) != 0U));
        if (fields[2][0] != 'A') { return; }
        GenericNmeaParser_PositionSet(parser, fields[3], fields[4], fields[5], fields[6]);
        GenericNmeaParser_VelocitySet(parser, fields[8], fields[7]);
    }
    else if ((strcmp(&fields[0][2], "VTG") == 0) && (count >= 6U) &&
             (parser->has_epoch != 0U) &&
             (receive_us >= parser->last_receive_us) &&
             (receive_us - parser->last_receive_us <=
              GENERIC_NMEA_AUX_MAX_LAG_US))
    { GenericNmeaParser_VelocitySet(parser, fields[1], fields[5]); }
    else if ((strcmp(&fields[0][2], "GST") == 0) && (count >= 9U) &&
             (parser->has_epoch != 0U) &&
             (GenericNmeaParser_UtcGet(fields[1], &epoch) != 0U) &&
             (epoch == parser->epoch))
    {
        float lat_std;
        float lon_std;
        if ((GenericNmeaParser_DecimalGet(fields[6], &lat_std) != 0U) &&
            (GenericNmeaParser_DecimalGet(fields[7], &lon_std) != 0U) &&
            (lat_std >= 0.0F) && (lon_std >= 0.0F))
        { parser->pending.horizontal_accuracy_m = hypotf(lat_std, lon_std);
          parser->valid_fields |= SYSTEM_GNSS_FIELD_HORIZONTAL_ACCURACY; }
        if ((GenericNmeaParser_DecimalGet(fields[8], &value) != 0U) && (value >= 0.0F))
        { parser->pending.vertical_accuracy_m = value;
          parser->valid_fields |= SYSTEM_GNSS_FIELD_VERTICAL_ACCURACY; }
    }
    else { /* GSA DOP is not metric position accuracy. */ }
}

static void GenericNmeaParser_SentenceCheck(GenericNmeaParser *parser,
    uint64_t receive_us)
{
    uint8_t checksum = 0U;
    uint8_t index;
    int8_t high;
    int8_t low;
    if (parser->length < 9U) { parser->resync_count++; return; }
    for (index = 1U; (index < parser->length) &&
         (parser->sentence[index] != '*'); index++)
    { checksum ^= (uint8_t)parser->sentence[index]; }
    if ((index + 3U != parser->length) ||
        ((high = GenericNmeaParser_HexDigit(parser->sentence[index + 1U])) < 0) ||
        ((low = GenericNmeaParser_HexDigit(parser->sentence[index + 2U])) < 0) ||
        (checksum != (uint8_t)(((uint8_t)high << 4U) | (uint8_t)low)))
    { parser->checksum_errors++; return; }
    parser->sentence[index] = '\0';
    parser->accepted_sentences++;
    GenericNmeaParser_SentenceApply(parser, &parser->sentence[1], receive_us);
}

void GenericNmeaParser_Init(GenericNmeaParser *parser)
{
    if (parser != NULL) { (void)memset(parser, 0, sizeof(*parser)); }
}

GenericNmeaFeedResult GenericNmeaParser_Feed(GenericNmeaParser *parser,
    const uint8_t *bytes, uint16_t length, uint64_t receive_us)
{
    uint16_t index;
    uint8_t sentences = 0U;
    if ((parser == NULL) || ((bytes == NULL) && (length != 0U)))
    { return GenericNmeaFeedInvalidArgument; }
    if (length > GENERIC_NMEA_MAX_BYTES_PER_PROCESS)
    { return GenericNmeaFeedLimitExceeded; }
    for (index = 0U; index < length; index++)
    {
        uint8_t byte = bytes[index];
        if (byte == '$')
        {
            if (parser->collecting != 0U) { parser->resync_count++; }
            parser->collecting = 1U;
            parser->length = 0U;
        }
        if (parser->collecting == 0U) { continue; }
        if (byte == '\n')
        {
            if (sentences >= GENERIC_NMEA_MAX_SENTENCES_PER_PROCESS)
            { parser->collecting = 0U; parser->resync_count++;
              return GenericNmeaFeedLimitExceeded; }
            if ((parser->length != 0U) &&
                (parser->sentence[parser->length - 1U] == '\r'))
            { parser->length--; }
            parser->sentence[parser->length] = '\0';
            GenericNmeaParser_SentenceCheck(parser, receive_us);
            sentences++;
            parser->collecting = 0U;
            parser->length = 0U;
        }
        else if (((byte < 32U) && (byte != '\r')) || (byte > 126U))
        { parser->collecting = 0U; parser->resync_count++; }
        else if (parser->length >= GENERIC_NMEA_MAX_SENTENCE)
        { parser->collecting = 0U; parser->overlength_sentences++; }
        else { parser->sentence[parser->length++] = (char)byte; }
    }
    return GenericNmeaFeedOk;
}
