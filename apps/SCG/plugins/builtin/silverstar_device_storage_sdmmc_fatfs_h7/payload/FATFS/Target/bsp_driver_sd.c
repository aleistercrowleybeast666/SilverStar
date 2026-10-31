/* SilverStar-owned exact H743 SDMMC1 adapter; original CubeMX glue is retained
 * outside the active source graph. HAL owns IDMA, never a runtime registry. */
#include "bsp_driver_sd.h"
#include "sdmmc.h"
#include "platform_memory.h"
#include <stddef.h>
#include <string.h>

#define SD_H7_SECTOR_BYTES 512U
#define SD_H7_CACHE_LINE_BYTES 32U

static uint8_t SdH7_ConfigurationValid(void)
{
    return (uint8_t)((hsd1.Instance == SDMMC1) &&
        ((SCB->CCR & SCB_CCR_DC_Msk) == 0U));
}

uint8_t BSP_SD_Init(void)
{
    if ((SdH7_ConfigurationValid() == 0U) || (BSP_PlatformIsDetected() == 0U))
    { return MSD_ERROR; }
    if (HAL_SD_Init(&hsd1) != HAL_OK) { return MSD_ERROR; }
    return (HAL_SD_ConfigWideBusOperation(&hsd1, SDMMC_BUS_WIDE_4B) == HAL_OK)
        ? MSD_OK : MSD_ERROR;
}

static uint8_t SdH7_RequestValid(const uint32_t *buffer, uint32_t sector,
    uint32_t count)
{
    HAL_SD_CardInfoTypeDef info = {0};
    if ((SdH7_ConfigurationValid() == 0U) || (buffer == NULL) || (count != 1U) ||
        (((uintptr_t)buffer % SD_H7_CACHE_LINE_BYTES) != 0U) ||
        (PlatformMemory_IsDmaAccessible(buffer, SD_H7_SECTOR_BYTES) == 0U))
    { return 0U; }
    if (HAL_SD_GetCardInfo(&hsd1, &info) != HAL_OK) { return 0U; }
    return (uint8_t)((info.LogBlockSize == SD_H7_SECTOR_BYTES) &&
        (sector < info.LogBlockNbr));
}

uint8_t BSP_SD_ReadBlocks_DMA(uint32_t *buffer, uint32_t sector, uint32_t count)
{
    if (SdH7_RequestValid(buffer, sector, count) == 0U) { return MSD_ERROR; }
    __DMB(); /* Publish scratch and transfer state before granting IDMA ownership. */
    return (HAL_SD_ReadBlocks_DMA(&hsd1, (uint8_t *)buffer, sector, count) == HAL_OK)
        ? MSD_OK : MSD_ERROR;
}

uint8_t BSP_SD_WriteBlocks_DMA(uint32_t *buffer, uint32_t sector, uint32_t count)
{
    if (SdH7_RequestValid(buffer, sector, count) == 0U) { return MSD_ERROR; }
    __DMB();
    return (HAL_SD_WriteBlocks_DMA(&hsd1, (uint8_t *)buffer, sector, count) == HAL_OK)
        ? MSD_OK : MSD_ERROR;
}

uint8_t BSP_SD_GetCardState(void)
{
    if (SdH7_ConfigurationValid() == 0U) { return SD_TRANSFER_BUSY; }
    return (HAL_SD_GetCardState(&hsd1) == HAL_SD_CARD_TRANSFER)
        ? SD_TRANSFER_OK : SD_TRANSFER_BUSY;
}

void BSP_SD_GetCardInfo(HAL_SD_CardInfoTypeDef *info)
{
    if (info == NULL) { return; }
    (void)memset(info, 0, sizeof(*info));
    if ((SdH7_ConfigurationValid() == 0U) || (HAL_SD_GetCardInfo(&hsd1, info) != HAL_OK))
    { (void)memset(info, 0, sizeof(*info)); }
}

void HAL_SD_AbortCallback(SD_HandleTypeDef *handle)
{
    if (handle == &hsd1) { BSP_SD_AbortCallback(); }
}

void HAL_SD_ErrorCallback(SD_HandleTypeDef *handle)
{
    if (handle == &hsd1) { BSP_SD_AbortCallback(); }
}

void HAL_SD_TxCpltCallback(SD_HandleTypeDef *handle)
{
    if (handle == &hsd1) { BSP_SD_WriteCpltCallback(); }
}

void HAL_SD_RxCpltCallback(SD_HandleTypeDef *handle)
{
    if (handle == &hsd1)
    {
        __DMB(); /* Observe completed DMA writes before waking the storage owner. */
        BSP_SD_ReadCpltCallback();
    }
}
