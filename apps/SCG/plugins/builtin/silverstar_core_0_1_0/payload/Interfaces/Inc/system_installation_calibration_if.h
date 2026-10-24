#ifndef __SYSTEM_INSTALLATION_CALIBRATION_IF_H
#define __SYSTEM_INSTALLATION_CALIBRATION_IF_H

/* SSIC v1 little-endian envelope, inside the SSOB generation/CRC double slot.
 * 0 magic; 4 schema; 5 kind; 6 algorithm; 7 coordinates; 8 descriptor u16;
 * 10 physical u16; 12 instance; 13..15 reserved; 16 configuration digest u32;
 * 20 driver hash u32; 24 model hash u32; 28 parent intrinsic CRC u32.
 * Only magnetic intrinsics are implemented: parent CRC must be zero.
 * Future relative rotations must bind their parent intrinsic CRC AND install
 * configuration; replacement of either requires external revalidation.
 * This format does not assert that an extrinsic rotation has been measured. */
#define SYSTEM_INSTALLATION_CAL_SCHEMA 1U
#define SYSTEM_INSTALLATION_CAL_HEADER_BYTES 32U

typedef enum
{
    SystemInstallationCalibrationKind_MagEllipsoid = 1U,
    /* Immutable full software candidate, never an active correction. Common
     * 32-byte SSIC header; length/CRC + canonical snapshot follow it. Header
     * driver/model/parent hash zeros are explicit unknown/not-single-parent;
     * complete identities, both parent contents and SHA binding are in body. */
    SystemInstallationCalibrationKind_CompleteCandidate = 2U
} SystemInstallationCalibrationKind;

/* Physical microtesla in the provider's body-b axes, before correction:
 * output_b = matrix * (input_b - bias_b). The configuration digest binds
 * the generated mounting/axis/transport configuration. Never compose an
 * old correction with a new one or apply this to an already-corrected sample. */
#define SYSTEM_INSTALLATION_CAL_MAG_ALGORITHM 1U
#define SYSTEM_INSTALLATION_CAL_BODY_UT_COORDINATES 1U
#define SYSTEM_INSTALLATION_CAL_NAMED_SNAPSHOT_COORDINATES 2U

#endif /* __SYSTEM_INSTALLATION_CALIBRATION_IF_H */
