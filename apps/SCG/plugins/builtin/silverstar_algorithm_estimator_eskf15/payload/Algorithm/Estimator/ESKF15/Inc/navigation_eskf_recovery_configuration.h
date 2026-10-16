#ifndef __NAVIGATION_ESKF_RECOVERY_CONFIGURATION_H
#define __NAVIGATION_ESKF_RECOVERY_CONFIGURATION_H

#include "navigation_eskf_recovery.h"
#include "navigation_eskf_recovery_qualifier.h"

#define NAV_ESKF_RECOVERY_CONFIGURATION_WIRE_SIZE 104U

typedef enum
{
    NAV_ESKF_RECOVERY_CONFIGURATION_COMPLETE = 0,
    NAV_ESKF_RECOVERY_CONFIGURATION_INVALID_ARGUMENT,
    NAV_ESKF_RECOVERY_CONFIGURATION_INVALID_POLICY,
    NAV_ESKF_RECOVERY_CONFIGURATION_IDENTITY_MISMATCH
} NavigationEskfRecoveryConfigurationResult;

typedef struct
{
    NavigationEskfRecoveryConfig policy;
    NavigationEskfRecoveryQualifierConfig qualifier;
    uint8_t enabled;
} NavigationEskfRecoveryConfiguration;

/* Immutable actual generated configuration, including disabled placeholders.
 * Caller never modifies this object or treats zero placeholders as approval. */
const NavigationEskfRecoveryConfiguration *NavigationEskfRecoveryConfiguration_Get(void);
/* No device IO. Checks the actual configuration checksum and, when enabled,
 * the complete policy. CRC identity is not a security or source-integrity proof. */
NavigationEskfRecoveryConfigurationResult NavigationEskfRecoveryConfiguration_Validate(void);
/* Wire authority: contracts/navigation_gnss_reacquisition_v1.json. All writes
 * fit104 bytes; invalid capacity/null/config overlap leaves output unchanged. */
NavigationEskfRecoveryConfigurationResult NavigationEskfRecoveryConfiguration_Encode(
    uint8_t *output, uint16_t capacity);

#endif /* __NAVIGATION_ESKF_RECOVERY_CONFIGURATION_H */
