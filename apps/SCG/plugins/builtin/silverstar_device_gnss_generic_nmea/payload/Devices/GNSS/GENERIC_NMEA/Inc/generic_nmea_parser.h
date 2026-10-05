#ifndef __GENERIC_NMEA_PARSER_H
#define __GENERIC_NMEA_PARSER_H

#include <stdint.h>
#include "system_gnss_if.h"

#define GENERIC_NMEA_MAX_SENTENCE 96U
#define GENERIC_NMEA_MAX_BYTES_PER_PROCESS 256U
#define GENERIC_NMEA_MAX_SENTENCES_PER_PROCESS 8U

typedef enum
{
    GenericNmeaFeedOk = 0,
    GenericNmeaFeedInvalidArgument,
    GenericNmeaFeedLimitExceeded
} GenericNmeaFeedResult;

typedef struct
{
    char sentence[GENERIC_NMEA_MAX_SENTENCE + 1U];
    uint8_t length;
    uint8_t collecting;
    uint8_t has_epoch;
    uint8_t has_published;
    uint32_t epoch;
    uint32_t sequence;
    uint32_t valid_fields;
    uint32_t supported_fields;
    uint32_t accepted_sentences;
    uint32_t checksum_errors;
    uint32_t overlength_sentences;
    uint32_t resync_count;
    uint64_t last_receive_us;
    SystemGnssSample pending;
    SystemGnssSample published;
} GenericNmeaParser;

void GenericNmeaParser_Init(GenericNmeaParser *parser);
GenericNmeaFeedResult GenericNmeaParser_Feed(GenericNmeaParser *parser,
    const uint8_t *bytes, uint16_t length, uint64_t receive_us);

#endif /* __GENERIC_NMEA_PARSER_H */
