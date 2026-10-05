/*
 * FCCG-owned STM32F4 FatFs disk I/O glue. The fixed SD_Driver table is the
 * vendor FatFs ABI, not a SilverStar runtime component registry.
 * Partial file sectors and read/modify/write remain owned by FatFs.
 */
#include "ff_gen_drv.h"
#include "sd_diskio.h"
#include "FreeRTOS.h"
#include "queue.h"
#include "task.h"
#include "platform_memory.h"
#include <stddef.h>
#include <string.h>

#define SILVERSTAR_SD_DISKIO_BYTE_INTEGRITY 1U
#define SD_IO_SECTOR_BYTES 512U
#define SD_IO_SECTOR_WORDS (SD_IO_SECTOR_BYTES / sizeof(uint32_t))
#define SD_IO_MAX_SECTORS 128U
#define SD_IO_TIMEOUT_TICKS pdMS_TO_TICKS(30000U)
#define SD_IO_READ_COMPLETE 1U
#define SD_IO_WRITE_COMPLETE 2U

/* Always bounce: even aligned application RAM may be inaccessible to DMA.
 * F407 has no DCache. Never borrow the caller buffer after disk_* returns. */
static PLATFORM_DMA_ACCESSIBLE uint32_t s_sd_scratch[SD_IO_SECTOR_WORDS];
static StaticQueue_t s_sd_queue_control;
static uint8_t s_sd_queue_storage[sizeof(uint16_t)];
static QueueHandle_t s_sd_queue;
static volatile DSTATUS s_sd_status = STA_NOINIT;
static volatile uint8_t s_sd_busy;
static volatile uint8_t s_sd_poisoned;
static volatile uint8_t s_sd_transfer_active;

_Static_assert(sizeof(s_sd_scratch) == SD_IO_SECTOR_BYTES,
               "SD scratch must contain exactly one sector");

static DRESULT SdDiskIo_Claim(void)
{
    DRESULT result = RES_NOTRDY;
    taskENTER_CRITICAL();
    if ((s_sd_busy == 0U) && (s_sd_poisoned == 0U))
    {
        s_sd_busy = 1U;
        result = RES_OK;
    }
    taskEXIT_CRITICAL();
    return result;
}

static void SdDiskIo_Release(void)
{
    taskENTER_CRITICAL();
    s_sd_busy = 0U;
    taskEXIT_CRITICAL();
}

static DRESULT SdDiskIo_Fail(void)
{
    /* An uncertain transfer may still own scratch. No reinitialization or
     * later same-kind completion may release/reuse it before an MCU reset. */
    taskENTER_CRITICAL();
    s_sd_transfer_active = 0U;
    s_sd_poisoned = 1U;
    s_sd_status = STA_NOINIT;
    taskEXIT_CRITICAL();
    return RES_ERROR;
}

static DRESULT SdDiskIo_ReadyWait(TickType_t started)
{
    while ((TickType_t)(xTaskGetTickCount() - started) < SD_IO_TIMEOUT_TICKS)
    {
        if (BSP_SD_GetCardState() == SD_TRANSFER_OK) { return RES_OK; }
        vTaskDelay(1U);
    }
    return SdDiskIo_Fail();
}

static DRESULT SdDiskIo_CompletionWait(uint16_t expected, TickType_t started)
{
    uint16_t event = 0U;
    TickType_t elapsed = (TickType_t)(xTaskGetTickCount() - started);
    if ((elapsed >= SD_IO_TIMEOUT_TICKS) ||
        (xQueueReceive(s_sd_queue, &event, SD_IO_TIMEOUT_TICKS - elapsed) != pdPASS) ||
        (event != expected))
    { return SdDiskIo_Fail(); }
    s_sd_transfer_active = 0U;
    return SdDiskIo_ReadyWait(started);
}

static DRESULT SdDiskIo_SectorRead(DWORD sector, TickType_t started)
{
    (void)xQueueReset(s_sd_queue);
    s_sd_transfer_active = 1U;
    if (BSP_SD_ReadBlocks_DMA(s_sd_scratch, (uint32_t)sector, 1U) != MSD_OK)
    { return SdDiskIo_Fail(); }
    return SdDiskIo_CompletionWait(SD_IO_READ_COMPLETE, started);
}

static DRESULT SdDiskIo_SectorWrite(DWORD sector, TickType_t started)
{
    (void)xQueueReset(s_sd_queue);
    s_sd_transfer_active = 1U;
    if (BSP_SD_WriteBlocks_DMA(s_sd_scratch, (uint32_t)sector, 1U) != MSD_OK)
    { return SdDiskIo_Fail(); }
    return SdDiskIo_CompletionWait(SD_IO_WRITE_COMPLETE, started);
}

DSTATUS SD_initialize(BYTE lun)
{
    if ((lun != 0U) || (xTaskGetSchedulerState() != taskSCHEDULER_RUNNING) ||
        (SdDiskIo_Claim() != RES_OK)) { return STA_NOINIT; }
    if ((s_sd_status & STA_NOINIT) != 0U)
    {
        if (s_sd_queue == NULL)
        {
            s_sd_queue = xQueueCreateStatic(1U, sizeof(uint16_t),
                s_sd_queue_storage, &s_sd_queue_control);
        }
        if ((s_sd_queue != NULL) && (BSP_SD_Init() == MSD_OK) &&
            (BSP_SD_GetCardState() == SD_TRANSFER_OK))
        { s_sd_status = 0U; }
    }
    SdDiskIo_Release();
    return s_sd_status;
}

DSTATUS SD_status(BYTE lun)
{
    if ((lun != 0U) || (s_sd_poisoned != 0U)) { return STA_NOINIT; }
    return s_sd_status;
}

static DRESULT SdDiskIo_RequestValidate(BYTE lun, const void *buffer,
    DWORD sector, UINT count)
{
    if ((lun != 0U) || (buffer == NULL) || (count == 0U) ||
        (count > SD_IO_MAX_SECTORS) || (sector > UINT32_MAX - (count - 1U)))
    { return RES_PARERR; }
    if ((s_sd_status & STA_NOINIT) != 0U) { return RES_NOTRDY; }
    return SdDiskIo_Claim();
}

DRESULT SD_read(BYTE lun, BYTE *buffer, DWORD sector, UINT count)
{
    UINT index;
    TickType_t started = xTaskGetTickCount();
    DRESULT result = SdDiskIo_RequestValidate(lun, buffer, sector, count);
    if (result != RES_OK) { return result; }
    result = SdDiskIo_ReadyWait(started);
    for (index = 0U; (index < count) && (result == RES_OK); index++)
    {
        result = SdDiskIo_SectorRead(sector + index, started);
        if (result == RES_OK)
        { (void)memcpy(buffer + index * SD_IO_SECTOR_BYTES, s_sd_scratch, SD_IO_SECTOR_BYTES); }
    }
    SdDiskIo_Release();
    return result;
}

#if _USE_WRITE == 1
DRESULT SD_write(BYTE lun, const BYTE *buffer, DWORD sector, UINT count)
{
    UINT index;
    TickType_t started = xTaskGetTickCount();
    DRESULT result = SdDiskIo_RequestValidate(lun, buffer, sector, count);
    if (result != RES_OK) { return result; }
    result = SdDiskIo_ReadyWait(started);
    for (index = 0U; (index < count) && (result == RES_OK); index++)
    {
        (void)memcpy(s_sd_scratch, buffer + index * SD_IO_SECTOR_BYTES, SD_IO_SECTOR_BYTES);
        result = SdDiskIo_SectorWrite(sector + index, started);
    }
    SdDiskIo_Release();
    return result;
}
#endif

#if _USE_IOCTL == 1
DRESULT SD_ioctl(BYTE lun, BYTE command, void *buffer)
{
    BSP_SD_CardInfo info;
    DRESULT result;
    if ((lun != 0U) || ((command != CTRL_SYNC) && (buffer == NULL))) { return RES_PARERR; }
    if ((s_sd_status & STA_NOINIT) != 0U) { return RES_NOTRDY; }
    result = SdDiskIo_Claim();
    if (result != RES_OK) { return result; }
    result = SdDiskIo_ReadyWait(xTaskGetTickCount());
    if ((result == RES_OK) && (command != CTRL_SYNC))
    {
        BSP_SD_GetCardInfo(&info);
        switch (command)
        {
            case GET_SECTOR_COUNT: *(DWORD *)buffer = info.LogBlockNbr; break;
            case GET_SECTOR_SIZE: *(WORD *)buffer = SD_IO_SECTOR_BYTES; break;
            case GET_BLOCK_SIZE: *(DWORD *)buffer = 1U; break;
            default: result = RES_PARERR; break;
        }
    }
    SdDiskIo_Release();
    return result;
}
#endif

static void SdDiskIo_CompleteFromIsr(uint16_t event)
{
    BaseType_t woken = pdFALSE;
    if ((s_sd_queue != NULL) && (s_sd_transfer_active != 0U))
    {
        (void)xQueueSendFromISR(s_sd_queue, &event, &woken);
        portYIELD_FROM_ISR(woken);
    }
}

/* The CubeMX BSP callbacks already filter the actual SD handle before routing. */
void BSP_SD_WriteCpltCallback(void) { SdDiskIo_CompleteFromIsr(SD_IO_WRITE_COMPLETE); }
void BSP_SD_ReadCpltCallback(void) { SdDiskIo_CompleteFromIsr(SD_IO_READ_COMPLETE); }

const Diskio_drvTypeDef SD_Driver = {
    SD_initialize, SD_status, SD_read,
#if _USE_WRITE == 1
    SD_write,
#endif
#if _USE_IOCTL == 1
    SD_ioctl,
#endif
};
