#ifndef __BSP_DRIVER_SD_H
#define __BSP_DRIVER_SD_H
#include <stdint.h>
typedef struct { void *Instance; } SD_HandleTypeDef;
typedef struct { uint32_t LogBlockNbr; uint32_t LogBlockSize; } HAL_SD_CardInfoTypeDef;
typedef struct { uint32_t CCR; } SCB_Type;
typedef enum { HAL_OK = 0, HAL_ERROR = 1 } HAL_StatusTypeDef;
extern SCB_Type s_test_scb;
extern uint32_t s_test_sdmmc;
#define SCB (&s_test_scb)
#define SDMMC1 (&s_test_sdmmc)
#define SCB_CCR_DC_Msk 0x10000U
#define SDMMC_BUS_WIDE_4B 2U
#define HAL_SD_CARD_TRANSFER 4U
#define MSD_OK 0U
#define MSD_ERROR 1U
#define SD_TRANSFER_OK 0U
#define SD_TRANSFER_BUSY 1U
void __DMB(void);
uint8_t BSP_PlatformIsDetected(void);
HAL_StatusTypeDef HAL_SD_Init(SD_HandleTypeDef *handle);
HAL_StatusTypeDef HAL_SD_ConfigWideBusOperation(SD_HandleTypeDef *handle, uint32_t width);
HAL_StatusTypeDef HAL_SD_GetCardInfo(SD_HandleTypeDef *handle, HAL_SD_CardInfoTypeDef *info);
HAL_StatusTypeDef HAL_SD_ReadBlocks_DMA(SD_HandleTypeDef *handle, uint8_t *buffer, uint32_t sector, uint32_t count);
HAL_StatusTypeDef HAL_SD_WriteBlocks_DMA(SD_HandleTypeDef *handle, uint8_t *buffer, uint32_t sector, uint32_t count);
uint32_t HAL_SD_GetCardState(SD_HandleTypeDef *handle);
void BSP_SD_AbortCallback(void);
void BSP_SD_WriteCpltCallback(void);
void BSP_SD_ReadCpltCallback(void);
uint8_t BSP_SD_Init(void);
uint8_t BSP_SD_ReadBlocks_DMA(uint32_t *buffer, uint32_t sector, uint32_t count);
uint8_t BSP_SD_WriteBlocks_DMA(uint32_t *buffer, uint32_t sector, uint32_t count);
uint8_t BSP_SD_GetCardState(void);
void BSP_SD_GetCardInfo(HAL_SD_CardInfoTypeDef *info);
void HAL_SD_AbortCallback(SD_HandleTypeDef *handle);
void HAL_SD_ErrorCallback(SD_HandleTypeDef *handle);
void HAL_SD_TxCpltCallback(SD_HandleTypeDef *handle);
void HAL_SD_RxCpltCallback(SD_HandleTypeDef *handle);
#endif
