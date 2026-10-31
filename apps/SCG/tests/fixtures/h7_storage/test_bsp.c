/* Test-only HAL boundary; no claim of electrical/cache hardware execution. */
#include "bsp_driver_sd.h"
#include "sdmmc.h"
#include "platform_memory.h"
#include <stdio.h>
#include <stdlib.h>

SCB_Type s_test_scb;
uint32_t s_test_sdmmc;
SD_HandleTypeDef hsd1 = {SDMMC1};
static uint8_t s_present = 1U;
static uint8_t s_accessible = 1U;
static HAL_StatusTypeDef s_result = HAL_OK;
static HAL_StatusTypeDef s_dma_result = HAL_OK;
static uint32_t s_state = HAL_SD_CARD_TRANSFER;
static uint32_t s_started;
static uint32_t s_barriers;
static uint32_t s_rx, s_tx, s_failed;
#define CHECK(c) do { if (!(c)) { fprintf(stderr,"line %d: %s\n",__LINE__,#c); exit(1); } } while (0)

void __DMB(void) { s_barriers++; }

uint8_t BSP_PlatformIsDetected(void) { return s_present; }
HAL_StatusTypeDef HAL_SD_Init(SD_HandleTypeDef *handle)
{ CHECK(handle == &hsd1); return s_result; }
HAL_StatusTypeDef HAL_SD_ConfigWideBusOperation(SD_HandleTypeDef *handle, uint32_t width)
{ CHECK(handle == &hsd1 && width == SDMMC_BUS_WIDE_4B); return s_result; }
HAL_StatusTypeDef HAL_SD_GetCardInfo(SD_HandleTypeDef *handle, HAL_SD_CardInfoTypeDef *info)
{ CHECK(handle == &hsd1); info->LogBlockNbr = 16U; info->LogBlockSize = 512U; return s_result; }
HAL_StatusTypeDef HAL_SD_ReadBlocks_DMA(SD_HandleTypeDef *handle, uint8_t *buffer, uint32_t sector, uint32_t count)
{ CHECK(handle == &hsd1 && buffer != NULL && sector < 16U && count == 1U); CHECK(s_barriers > s_started); s_started++; return s_dma_result; }
HAL_StatusTypeDef HAL_SD_WriteBlocks_DMA(SD_HandleTypeDef *handle, uint8_t *buffer, uint32_t sector, uint32_t count)
{ return HAL_SD_ReadBlocks_DMA(handle, buffer, sector, count); }
uint32_t HAL_SD_GetCardState(SD_HandleTypeDef *handle)
{ CHECK(handle == &hsd1); return s_state; }
uint8_t PlatformMemory_IsDmaAccessible(const void *buffer, size_t length)
{ CHECK(buffer != NULL && length == 512U); return s_accessible; }
void BSP_SD_AbortCallback(void) { s_failed++; }
void BSP_SD_ReadCpltCallback(void) { s_rx++; }
void BSP_SD_WriteCpltCallback(void) { s_tx++; }

int main(void)
{
    _Alignas(32) uint32_t buffer[128];
    SD_HandleTypeDef other = {SDMMC1};
    HAL_SD_CardInfoTypeDef info;
    CHECK(BSP_SD_Init() == MSD_OK);
    CHECK(BSP_SD_ReadBlocks_DMA(buffer, 0U, 1U) == MSD_OK);
    CHECK(BSP_SD_WriteBlocks_DMA(buffer, 15U, 1U) == MSD_OK);
    CHECK(s_started == 2U);
    HAL_SD_RxCpltCallback(&other); HAL_SD_TxCpltCallback(&other);
    HAL_SD_AbortCallback(NULL); HAL_SD_ErrorCallback(&other);
    CHECK(s_rx == 0U && s_tx == 0U && s_failed == 0U);
    HAL_SD_RxCpltCallback(&hsd1); HAL_SD_TxCpltCallback(&hsd1);
    HAL_SD_ErrorCallback(&hsd1); HAL_SD_AbortCallback(&hsd1);
    CHECK(s_rx == 1U && s_tx == 1U && s_failed == 2U);
    s_test_scb.CCR = SCB_CCR_DC_Msk;
    CHECK(BSP_SD_Init() == MSD_ERROR);
    CHECK(BSP_SD_ReadBlocks_DMA(buffer, 0U, 1U) == MSD_ERROR);
    CHECK(BSP_SD_GetCardState() == SD_TRANSFER_BUSY);
    s_test_scb.CCR = 0U;
    CHECK(BSP_SD_ReadBlocks_DMA(NULL, 0U, 1U) == MSD_ERROR);
    CHECK(BSP_SD_ReadBlocks_DMA(buffer + 1U, 0U, 1U) == MSD_ERROR);
    CHECK(BSP_SD_ReadBlocks_DMA(buffer, 0U, 2U) == MSD_ERROR);
    CHECK(BSP_SD_WriteBlocks_DMA(buffer, 16U, 1U) == MSD_ERROR);
    s_accessible = 0U;
    CHECK(BSP_SD_WriteBlocks_DMA(buffer, 0U, 1U) == MSD_ERROR);
    s_accessible = 1U;
    CHECK(s_started == 2U);
    s_dma_result = HAL_ERROR;
    CHECK(BSP_SD_WriteBlocks_DMA(buffer, 0U, 1U) == MSD_ERROR);
    CHECK(s_started == 3U);
    s_dma_result = HAL_OK;
    s_result = HAL_ERROR;
    CHECK(BSP_SD_Init() == MSD_ERROR);
    BSP_SD_GetCardInfo(&info);
    CHECK(info.LogBlockNbr == 0U && info.LogBlockSize == 0U);
    CHECK(BSP_SD_ReadBlocks_DMA(buffer, 0U, 1U) == MSD_ERROR);
    s_result = HAL_OK; s_present = 0U;
    CHECK(BSP_SD_Init() == MSD_ERROR);
    hsd1.Instance = NULL;
    CHECK(BSP_SD_ReadBlocks_DMA(buffer, 0U, 1U) == MSD_ERROR);
    CHECK(s_started == 3U);
    puts("H7 BSP normal/foreign-handle/error/cache/memory/range failures passed");
    return 0;
}
