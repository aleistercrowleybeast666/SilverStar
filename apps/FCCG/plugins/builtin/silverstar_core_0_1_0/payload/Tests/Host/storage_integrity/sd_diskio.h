#ifndef __SD_DISKIO_H
#define __SD_DISKIO_H
#include <stdint.h>
#include "ff_gen_drv.h"
#define MSD_OK 0U
#define MSD_ERROR 1U
#define SD_TRANSFER_OK 0U
#define BLOCKSIZE 512U
typedef struct { uint32_t LogBlockNbr; uint32_t LogBlockSize; } BSP_SD_CardInfo;
uint8_t BSP_SD_Init(void);
uint8_t BSP_SD_GetCardState(void);
void BSP_SD_GetCardInfo(BSP_SD_CardInfo *info);
uint8_t BSP_SD_ReadBlocks_DMA(uint32_t *buffer, uint32_t sector, uint32_t count);
uint8_t BSP_SD_WriteBlocks_DMA(uint32_t *buffer, uint32_t sector, uint32_t count);
void BSP_SD_ReadCpltCallback(void);
void BSP_SD_WriteCpltCallback(void);
extern const Diskio_drvTypeDef SD_Driver;
#endif
