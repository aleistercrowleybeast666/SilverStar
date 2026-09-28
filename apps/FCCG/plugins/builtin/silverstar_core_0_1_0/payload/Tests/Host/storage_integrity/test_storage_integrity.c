/* Real FatFs + diskio + SSLOG codec, with a delayed, word-aligned DMA model. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "ff.h"
#include "sd_diskio.h"
#include "queue.h"
#include "task.h"
#include "sslog_protocol.h"
#include "../../Target/storage_integrity.h"

#define CARD_SECTORS 65536U
#define TEST_RECORD_COUNT 40000U
static uint8_t s_card[CARD_SECTORS * BLOCKSIZE];
static FATFS s_fs;
static FIL s_file;
static uint8_t s_work[BLOCKSIZE];
static TickType_t s_ticks;
static QueueHandle_t s_queue;
static uint8_t *s_dma_buffer;
static uint32_t s_dma_sector;
static uint32_t s_dma_count;
static uint32_t s_dma_unaligned;
static uint32_t s_dma_transactions;
static uint8_t s_dma_write;
static uint8_t s_dma_pending;
static uint8_t s_timeout;
static uint8_t s_wrong_event;
static uint8_t s_start_failure;
static uint8_t s_card_busy;
static unsigned s_failures;

#define CHECK(condition) do { if (!(condition)) { \
    fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #condition); \
    s_failures++; return 0; } } while (0)

TickType_t xTaskGetTickCount(void) { return s_ticks++; }
BaseType_t xTaskGetSchedulerState(void) { return taskSCHEDULER_RUNNING; }
void vTaskDelay(TickType_t ticks) { s_ticks += ticks; }
void Fixture_CriticalEnter(void) { }
void Fixture_CriticalExit(void) { }
DWORD get_fattime(void) { return (46UL << 25U) | (1UL << 21U) | (1UL << 16U); }

QueueHandle_t xQueueCreateStatic(UBaseType_t count, UBaseType_t size,
    uint8_t *storage, StaticQueue_t *control)
{
    (void)storage;
    if ((count > 16U) || (size != sizeof(uint16_t))) { abort(); }
    memset(control, 0, sizeof(*control));
    control->size = size;
    control->capacity = count;
    s_queue = control;
    return control;
}

BaseType_t xQueueSendFromISR(QueueHandle_t queue, const void *data,
    BaseType_t *woken)
{
    *woken = pdFALSE;
    if ((queue == NULL) || (queue->count >= queue->capacity)) { return pdFALSE; }
    memcpy(&queue->data[queue->count++], data, queue->size);
    return pdPASS;
}

BaseType_t xQueueReset(QueueHandle_t queue)
{
    queue->count = 0U;
    return pdPASS;
}

BaseType_t xQueueReceive(QueueHandle_t queue, void *data, TickType_t ticks)
{
    if ((ticks != 0U) && s_dma_pending && !s_timeout)
    {
        /* Data is consumed at completion, never when DMA is submitted. */
        uint8_t *aligned = (uint8_t *)((uintptr_t)s_dma_buffer & ~(uintptr_t)3U);
        if (s_dma_write)
        { memcpy(&s_card[s_dma_sector * BLOCKSIZE], aligned, s_dma_count * BLOCKSIZE); }
        else
        { memcpy(aligned, &s_card[s_dma_sector * BLOCKSIZE], s_dma_count * BLOCKSIZE); }
        s_dma_pending = 0U;
        s_ticks += 2U;
        if ((s_dma_write != 0U) != (s_wrong_event != 0U))
        { BSP_SD_WriteCpltCallback(); }
        else { BSP_SD_ReadCpltCallback(); }
    }
    if ((queue != NULL) && (queue->count != 0U))
    {
        memcpy(data, &queue->data[0], queue->size);
        queue->count--;
        memmove(&queue->data[0], &queue->data[1], queue->count * queue->size);
        return pdPASS;
    }
    s_ticks += ticks;
    return pdFALSE;
}

uint8_t BSP_SD_Init(void) { return MSD_OK; }
uint8_t BSP_SD_GetCardState(void) { return (s_dma_pending || s_card_busy) ? MSD_ERROR : SD_TRANSFER_OK; }
void BSP_SD_GetCardInfo(BSP_SD_CardInfo *info)
{ info->LogBlockNbr = CARD_SECTORS; info->LogBlockSize = BLOCKSIZE; }

static uint8_t Fixture_DmaStart(uint32_t *buffer, uint32_t sector,
    uint32_t count, uint8_t write)
{
    if (s_start_failure) { return MSD_ERROR; }
    if (s_dma_pending || (count == 0U) || (sector >= CARD_SECTORS) ||
        (count > CARD_SECTORS - sector)) { abort(); }
    s_dma_buffer = (uint8_t *)buffer;
    s_dma_sector = sector;
    s_dma_count = count;
    s_dma_write = write;
    s_dma_pending = 1U;
    s_dma_transactions++;
    s_dma_unaligned += (uint32_t)(((uintptr_t)buffer & 3U) != 0U);
    return MSD_OK;
}
uint8_t BSP_SD_ReadBlocks_DMA(uint32_t *buffer, uint32_t sector, uint32_t count)
{ return Fixture_DmaStart(buffer, sector, count, 0U); }
uint8_t BSP_SD_WriteBlocks_DMA(uint32_t *buffer, uint32_t sector, uint32_t count)
{ return Fixture_DmaStart(buffer, sector, count, 1U); }

static uint8_t Fixture_Byte(uint32_t offset)
{ return (uint8_t)((offset * 73U) ^ (offset >> 8U) ^ (offset >> 17U)); }

static int Test_ByteStream(void)
{
    static const UINT lengths[] = {1,2,3,4,7,31,60,88,91,119,127,255,256,257,511,512,513};
    _Alignas(32) uint8_t buffer[550];
    uint32_t offset = 0U;
    UINT transferred;
    unsigned index;
    CHECK(f_open(&s_file, "0:BYTES.BIN", FA_CREATE_NEW | FA_WRITE | FA_READ) == FR_OK);
    for (index = 0U; index < 10000U; index++)
    {
        UINT length = lengths[index % (sizeof(lengths) / sizeof(lengths[0]))];
        uint8_t *source = &buffer[1U + (index % 31U)];
        UINT i;
        for (i = 0U; i < length; i++) { source[i] = Fixture_Byte(offset + i); }
        CHECK(f_write(&s_file, source, length, &transferred) == FR_OK);
        CHECK(transferred == length);
        offset += length;
        if ((index % 13U) == 0U) { CHECK(f_sync(&s_file) == FR_OK); }
    }
    CHECK(f_size(&s_file) == offset);
    CHECK(f_sync(&s_file) == FR_OK);
    CHECK(f_close(&s_file) == FR_OK);
    printf("BYTE_WRITE_COMPLETE unaligned_dma=%lu\n", (unsigned long)s_dma_unaligned);
    CHECK(f_mount(NULL, "0:", 0U) == FR_OK);
    CHECK(f_mount(&s_fs, "0:", 1U) == FR_OK);
    CHECK(f_open(&s_file, "0:BYTES.BIN", FA_READ) == FR_OK);
    for (uint32_t read_offset = 0U; read_offset < offset;)
    {
        /* Aligned readback isolates corruption already persisted by writes.
         * RecordStream separately exercises unaligned reads and offsets. */
        UINT size = offset - read_offset > 512U ? 512U : offset - read_offset;
        CHECK(f_read(&s_file, buffer, size, &transferred) == FR_OK);
        CHECK(size == transferred);
        for (UINT i = 0U; i < size; i++)
        {
            if (buffer[i] != Fixture_Byte(read_offset + i))
            { fprintf(stderr, "byte mismatch at %lu; unaligned DMA=%lu\n",
                (unsigned long)(read_offset + i), (unsigned long)s_dma_unaligned); }
            CHECK(buffer[i] == Fixture_Byte(read_offset + i));
        }
        read_offset += size;
    }
    CHECK(f_read(&s_file, buffer, 1U, &transferred) == FR_OK);
    CHECK(transferred == 0U);
    CHECK(f_close(&s_file) == FR_OK);
    printf("BYTE_INTEGRITY bytes=%lu writes=10000 unaligned_dma=%lu\n",
        (unsigned long)offset, (unsigned long)s_dma_unaligned);
    return 1;
}

static int Test_RecordStream(const char *output)
{
    static const FlightLogRecordType types[] = {
        FLIGHT_LOG_RECORD_IMU_CORRECTED,
        FLIGHT_LOG_RECORD_GNSS_NATIVE, FLIGHT_LOG_RECORD_BARO_NATIVE,
        FLIGHT_LOG_RECORD_ALIGNMENT_RESULT,
        FLIGHT_LOG_RECORD_CALIBRATION_RESULT, FLIGHT_LOG_RECORD_MISSION_CONFIG,
        FLIGHT_LOG_RECORD_INITIAL_STATE, FLIGHT_LOG_RECORD_EVENT, FLIGHT_LOG_RECORD_STATS};
    FlightLogFileHeaderInfo info = {0};
    FlightLogRecord record;
    uint8_t buffer[FLIGHT_LOG_MAX_RECORD_SIZE + 32U];
    uint16_t length;
    UINT transferred;
    uint32_t expected_length = 0U;
    FILE *exported;
    uint8_t expected[FLIGHT_LOG_MAX_RECORD_SIZE];
    CHECK(FLIGHT_LOG_MISSION_CONFIG_PAYLOAD_SIZE == 91U);
    CHECK(f_open(&s_file, "0:MIX.BIN", FA_CREATE_NEW | FA_WRITE | FA_READ) == FR_OK);
    CHECK(FlightLog_FileHeaderSerialize(&info, buffer, sizeof(buffer), &length) == FLIGHT_LOG_SERIALIZE_RESULT_OK);
    CHECK(f_write(&s_file, buffer, length, &transferred) == FR_OK);
    CHECK(transferred == length);
    expected_length += length;
    for (uint32_t index = 0U; index < TEST_RECORD_COUNT; index++)
    {
        uint8_t *source = buffer + 1U + index % 31U;
        memset(&record, 0, sizeof(record));
        record.record_type = types[index % (sizeof(types) / sizeof(types[0]))];
        record.timestamp_us = 1000000ULL + index * 1000ULL;
        record.valid_flags = index;
        CHECK(FlightLog_RecordSerialize(&record, index, source,
            FLIGHT_LOG_MAX_RECORD_SIZE, &length) == FLIGHT_LOG_SERIALIZE_RESULT_OK);
        if (record.record_type == FLIGHT_LOG_RECORD_MISSION_CONFIG) { CHECK(length == 119U); }
        CHECK(f_write(&s_file, source, length, &transferred) == FR_OK);
        CHECK(length == transferred);
        expected_length += length;
        if ((index % 47U) == 0U) { CHECK(f_sync(&s_file) == FR_OK); }
    }
    CHECK(f_sync(&s_file) == FR_OK);
    CHECK(f_size(&s_file) == expected_length);
    CHECK(f_close(&s_file) == FR_OK);
    CHECK(f_mount(NULL, "0:", 0U) == FR_OK);
    CHECK(f_mount(&s_fs, "0:", 1U) == FR_OK);
    CHECK(f_open(&s_file, "0:MIX.BIN", FA_READ) == FR_OK);
    exported = fopen(output, "wb");
    CHECK(exported != NULL);
    CHECK(FlightLog_FileHeaderSerialize(&info, expected, sizeof(expected), &length) == FLIGHT_LOG_SERIALIZE_RESULT_OK);
    CHECK(f_read(&s_file, buffer + 1U, length, &transferred) == FR_OK);
    CHECK(transferred == length && memcmp(expected, buffer + 1U, length) == 0);
    CHECK(fwrite(buffer + 1U, 1U, length, exported) == length);
    for (uint32_t index = 0U; index < TEST_RECORD_COUNT; index++)
    {
        FlightLogRecord decoded;
        uint32_t sequence;
        uint16_t consumed;
        memset(&record, 0, sizeof(record));
        record.record_type = types[index % (sizeof(types) / sizeof(types[0]))];
        record.timestamp_us = 1000000ULL + index * 1000ULL;
        record.valid_flags = index;
        CHECK(FlightLog_RecordSerialize(&record, index, expected, sizeof(expected), &length) == FLIGHT_LOG_SERIALIZE_RESULT_OK);
        CHECK(f_read(&s_file, buffer + 1U, length, &transferred) == FR_OK);
        CHECK(transferred == length && memcmp(expected, buffer + 1U, length) == 0);
        CHECK(FlightLog_RecordDeserialize(buffer + 1U, length, &decoded, &sequence, &consumed) == FLIGHT_LOG_DESERIALIZE_RESULT_OK);
        CHECK(sequence == index && consumed == length);
        CHECK(fwrite(buffer + 1U, 1U, length, exported) == length);
    }
    CHECK(f_read(&s_file, buffer, 1U, &transferred) == FR_OK && transferred == 0U);
    CHECK(fclose(exported) == 0);
    CHECK(f_close(&s_file) == FR_OK);
    printf("SSLOG_MIX records=%u bytes=%lu transactions=%lu\n", TEST_RECORD_COUNT,
        (unsigned long)expected_length, (unsigned long)s_dma_transactions);
    return 1;
}

static int Test_DiskFailure(const char *mode)
{
    uint8_t buffer[513];
    uint8_t scratch_before[512];
    uint32_t transactions;
    DRESULT result;
    memset(buffer, 0xA7, sizeof(buffer));
    CHECK(SD_Driver.disk_write(0U, NULL, 20000U, 1U) == RES_PARERR);
    CHECK(SD_Driver.disk_write(0U, buffer, 20000U, 0U) == RES_PARERR);
    CHECK(SD_Driver.disk_read(0U, buffer, UINT32_MAX, 2U) == RES_PARERR);
    BSP_SD_WriteCpltCallback(); /* Inactive stale completion must not satisfy I/O. */
    BSP_SD_ReadCpltCallback();
    CHECK(SD_Driver.disk_write(0U, buffer + 1U, 20000U, 1U) == RES_OK);
    if (strstr(mode, "timeout") != NULL) { s_timeout = 1U; }
    if (strstr(mode, "wrong") != NULL) { s_wrong_event = 1U; }
    if (strstr(mode, "start") != NULL) { s_start_failure = 1U; }
    if (strcmp(mode, "sync-timeout") == 0)
    {
        s_card_busy = 1U;
        result = SD_Driver.disk_ioctl(0U, CTRL_SYNC, NULL);
    }
    else if (strstr(mode, "read") != NULL)
    { result = SD_Driver.disk_read(0U, buffer + 1U, 20000U, 1U); }
    else { result = SD_Driver.disk_write(0U, buffer + 1U, 20000U, 1U); }
    CHECK(result == RES_ERROR);
    memcpy(scratch_before, s_dma_buffer, sizeof(scratch_before));
    transactions = s_dma_transactions;
    s_timeout = 0U;
    s_wrong_event = 0U;
    s_start_failure = 0U;
    s_card_busy = 0U;
    BSP_SD_WriteCpltCallback(); /* Late IRQ cannot unpoison or reuse scratch. */
    BSP_SD_ReadCpltCallback();
    CHECK((SD_Driver.disk_initialize(0U) & STA_NOINIT) != 0U);
    CHECK(SD_Driver.disk_write(0U, buffer + 1U, 20001U, 1U) == RES_NOTRDY);
    CHECK(SD_Driver.disk_read(0U, buffer + 1U, 20001U, 1U) == RES_NOTRDY);
    CHECK(s_dma_transactions == transactions);
    CHECK(memcmp(scratch_before, s_dma_buffer, sizeof(scratch_before)) == 0);
    printf("DISK_FAILURE mode=%s bounded_ticks=%lu no_reuse=1\n", mode, (unsigned long)s_ticks);
    return 1;
}

int main(int argc, char **argv)
{
    char path[4];
    if (argc != 2 && argc != 3) { return 2; }
    if (FATFS_LinkDriver(&SD_Driver, path) != 0U) { return 3; }
    if (f_mkfs(path, FM_FAT | FM_SFD, 512U, s_work, sizeof(s_work)) != FR_OK) { return 4; }
    if (f_mount(&s_fs, path, 1U) != FR_OK) { return 5; }
    if (strcmp(argv[1], "--target-bench") == 0)
    {
        StorageIntegrityResult result = StorageIntegrity_Run();
        printf("TARGET_BENCH_HOST result=%u\n", (unsigned)result);
        return result == StorageIntegrityResult_Ok ? 0 : 1;
    }
    if (argc == 3) { return Test_DiskFailure(argv[2]) ? 0 : 1; }
    if (!Test_ByteStream() || !Test_RecordStream(argv[1])) { return 1; }
    return s_failures ? 1 : 0;
}
