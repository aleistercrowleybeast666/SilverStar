#include <stdint.h>
typedef enum { LoraDeactivateResult_Ok, LoraDeactivateResult_PortError } LoraDeactivateResult;
LoraDeactivateResult Lora_Deactivate(uint8_t instance);
typedef enum { LORA_DIAG_RESULT_OK, LORA_DIAG_RESULT_NOT_INIT } LoraDiagResult;
typedef struct { uint16_t firmware_version; uint8_t status_value; uint8_t verified; } LoraChipStatus;
LoraDiagResult Lora_ChipStatusGet(uint8_t instance, LoraChipStatus *status);
