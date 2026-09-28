#ifndef __PROJECT_LOG_DECODER_PROFILE_H
#define __PROJECT_LOG_DECODER_PROFILE_H

#include <stdint.h>

#define PROJECT_LOG_DECODER_HASH_SIZE 16U

typedef struct
{
    uint16_t package_schema_major;
    uint16_t package_schema_minor;
    uint16_t container_format_major;
    uint16_t container_format_minor;
    uint8_t record_catalog_hash_128[PROJECT_LOG_DECODER_HASH_SIZE];
    uint8_t project_semantics_hash_128[PROJECT_LOG_DECODER_HASH_SIZE];
    uint8_t generation_profile_hash_128[PROJECT_LOG_DECODER_HASH_SIZE];
} ProjectLogDecoderProfile;

void ProjectLogDecoderProfile_Get(ProjectLogDecoderProfile *profile);

#endif /* __PROJECT_LOG_DECODER_PROFILE_H */
