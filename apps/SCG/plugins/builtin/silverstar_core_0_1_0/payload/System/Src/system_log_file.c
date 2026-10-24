#include "system_log_file.h"
#include "system_lifecycle.h"
#include "system_version.h"

#include <stddef.h>
#include <string.h>
#include "common_format.h"
#include "platform_critical.h"
#include "platform_memory.h"
#include "silverstar_assert.h"
#include "system_time.h"
#include "system_user_config.h"
#include "system_installation_capture_if.h"

#define LOG_FILE_IDLE_TIMEOUT_US 30000000ULL
#define LOG_FILE_META_QUANTA 8U
#define LOG_FILE_SERVICE_BUDGET_US 2000ULL
#define LOG_FILE_REQUEST_SIZE 192U
#define LOG_FILE_TOKEN_COUNT 7U
#define LOG_FILE_FORMAT_SIZE 256U
#define LOG_FILE_BLOCK_HEADER_SIZE 44U
#define LOG_FILE_BLOCK_RAW_SIZE 560U

typedef struct
{
    char text[LOG_FILE_REQUEST_SIZE];
    uint16_t offsets[LOG_FILE_TOKEN_COUNT];
    uint8_t count;
} LogFileTokens;

typedef enum
{
    LOG_FILE_IDLE = 0, LOG_FILE_PENDING, LOG_FILE_DONE
} LogFileState;
typedef enum
{
    LOG_FILE_LIST = 0, LOG_FILE_META, LOG_FILE_READ, LOG_FILE_BLOCK, LOG_FILE_BATCH, LOG_FILE_DELETE
} LogFileOperation;
typedef struct
{
    LogFileOperation operation;
    uint32_t id;
    uint32_t file_id;
    uint32_t crc;
    uint32_t size;
    uint32_t offset;
    uint32_t transfer_low;
    uint32_t transfer_high;
    uint32_t block_sequence;
} LogFileRequest;
typedef struct
{
    LogFileState state;
    LogFileRequest request;
    uint64_t last_poll_us;
    uint32_t sequence;
    uint8_t cancelled;
    uint8_t lease_owned;
    uint8_t cleanup_failed;
    uint8_t batch_left;
    uint8_t batch_claimed;
    union
    {
        char text[LOG_FILE_FORMAT_SIZE];
        uint8_t block[LOG_FILE_BLOCK_RAW_SIZE];
    } response;
    uint16_t block_length;
} LogFileMailbox;
typedef struct
{
    uint32_t request_id;
    uint32_t file_id;
    uint32_t crc;
    uint32_t size;
    uint32_t count;
    uint32_t cursor;
    uint8_t hashing;
    uint8_t cached;
} LogFileWorker;

typedef union
{
    uint8_t data[SYSTEM_LOG_FILE_HASH_QUANTUM];
    char result[LOG_FILE_FORMAT_SIZE];
    uint8_t block[LOG_FILE_BLOCK_RAW_SIZE];
} LogFileScratch;

/* The selected storage adapters copy through their private DMA bounce sector.
 * Mailbox, hash bytes and formatter storage remain CPU-only. */
static PLATFORM_CPU_FAST_BSS LogFileMailbox s_mailbox;
static PLATFORM_CPU_FAST_BSS LogFileWorker s_worker;
/* LoggerTask owns scratch. Hash bytes are consumed before formatting. READ
 * copies all bytes to local hex and computes CRC before writing result. The
 * independent mailbox alone is shared with SerialTask. Maximum READ text is
 * 255 bytes plus NUL (uint32 IDs/offset, six-digit file ID, 64-byte hex data). */
static PLATFORM_CPU_FAST_BSS LogFileScratch s_scratch;
static PLATFORM_CPU_FAST_BSS SystemLogFileSnapshot s_snapshot;
/* LoggerTask reuses scratch, then publishes a raw block into the mailbox union.
 * SerialTask copies it under the lock, then encodes only in its caller-owned
 * Console buffer. No extra raw+wire buffers or interrupt-disabled encoding. */
/* SerialTask-only one-call selector. A stale/cancelled mailbox is rechecked. */
static uint32_t s_binary_request;

void SystemLogFile_StatusPublish(const SystemLogFileSnapshot *snapshot)
{
    PlatformCriticalState lock;
    SILVERSTAR_ASSERT_OBJECT(snapshot, SystemLogFileSnapshot, SILVERSTAR_ASSERT_MODULE_SYSTEM);
    SILVERSTAR_ASSERT((snapshot->valid == 1U) && (snapshot->lifecycle <= SYSTEM_STATE_FAULT),
        SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    lock = PlatformCritical_Enter();
    s_snapshot = *snapshot;
    PlatformCritical_Exit(lock);
}

uint8_t SystemLogFile_StatusGet(SystemLogFileSnapshot *snapshot)
{
    PlatformCriticalState lock;
    if (snapshot == NULL) { return 0U; }
    lock = PlatformCritical_Enter();
    *snapshot = s_snapshot;
    PlatformCritical_Exit(lock);
    return snapshot->valid;
}

static const char *LogFile_OperationText(LogFileOperation operation)
{
    switch (operation)
    {
        case LOG_FILE_LIST: return "LIST";
        case LOG_FILE_META: return "META";
        case LOG_FILE_READ: return "READ";
        case LOG_FILE_BLOCK: return "BLOCK";
        case LOG_FILE_BATCH: return "BATCH";
        case LOG_FILE_DELETE: return "DELETE";
        default: return "UNKNOWN";
    }
}

static const char *LogFile_ResultText(SystemLogFileResult result)
{
    switch (result)
    {
        case SystemLogFileResult_Ok: return "OK";
        case SystemLogFileResult_Pending: return "PENDING";
        case SystemLogFileResult_BadArgument: return "BAD_ARGUMENT";
        case SystemLogFileResult_Busy: return "BUSY";
        case SystemLogFileResult_Locked: return "LOCKED";
        case SystemLogFileResult_NotReady: return "NOT_READY";
        case SystemLogFileResult_NotFound: return "NOT_FOUND";
        case SystemLogFileResult_Stale: return "STALE";
        case SystemLogFileResult_IoError: return "IO_ERROR";
        case SystemLogFileResult_Cancelled: return "CANCELLED";
        case SystemLogFileResult_Timeout: return "TIMEOUT";
        case SystemLogFileResult_Unsupported: return "UNSUPPORTED";
        default: return "IO_ERROR";
    }
}

static uint8_t LogFile_NumberParse(const char *text, uint32_t *number)
{
    uint8_t index;
    uint32_t value = 0U;
    if ((text == NULL) || (text[0] == '\0')) { return 0U; }
    for (index = 0U; index < 10U; index++)
    {
        uint8_t digit;
        if (text[index] == '\0') { *number = value; return 1U; }
        if ((text[index] < '0') || (text[index] > '9')) { return 0U; }
        digit = (uint8_t)(text[index] - '0');
        if (value > (UINT32_MAX - digit) / 10U) { return 0U; }
        value = value * 10U + digit;
    }
    if (text[10] != '\0') { return 0U; }
    *number = value;
    return 1U;
}

static uint8_t LogFile_HexParse(const char *text, uint32_t *number)
{
    uint8_t index;
    uint32_t value = 0U;
    for (index = 0U; index < 8U; index++)
    {
        char digit = text[index];
        value <<= 4U;
        if ((digit >= '0') && (digit <= '9')) { value |= (uint32_t)(digit - '0'); }
        else if ((digit >= 'A') && (digit <= 'F'))
        { value |= (uint32_t)(digit - 'A' + 10); }
        else { return 0U; }
    }
    *number = value;
    return 1U;
}

static uint8_t LogFile_TokenParse(const char *text, LogFileRequest *request)
{
    if ((strlen(text) != 19U) || (text[0] != '1') ||
        (text[1] != '-') || (text[10] != '-')) { return 0U; }
    return (uint8_t)((LogFile_HexParse(&text[2], &request->crc) != 0U) &&
        (LogFile_HexParse(&text[11], &request->size) != 0U));
}

static uint8_t LogFile_Tokenize(LogFileTokens *tokens)
{
    uint16_t index;
    uint8_t count = 0U;
    uint8_t in_token = 0U;
    for (index = 0U; index < LOG_FILE_REQUEST_SIZE; index++)
    {
        char value = tokens->text[index];
        if (value == '\0') { tokens->count = count; return count; }
        if ((value == ' ') || (value == '\t') || (value == '\r') || (value == '\n'))
        { tokens->text[index] = '\0'; in_token = 0U; }
        else if (in_token == 0U)
        {
            if (count >= LOG_FILE_TOKEN_COUNT) { return 0U; }
            tokens->offsets[count++] = index;
            in_token = 1U;
        }
    }
    return 0U;
}

static const char *LogFile_TokenGet(const LogFileTokens *tokens, uint8_t index)
{
    SILVERSTAR_ASSERT(index < tokens->count, SILVERSTAR_ASSERT_MODULE_SYSTEM,
        SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
    SILVERSTAR_ASSERT(tokens->offsets[index] < LOG_FILE_REQUEST_SIZE,
        SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
    return &tokens->text[tokens->offsets[index]];
}

static uint8_t LogFile_BlockRequestParse(const LogFileTokens *tokens,
    uint8_t count, LogFileRequest *request)
{
    const char *transfer;
    if ((count != 7U) || (strcmp(LogFile_TokenGet(tokens, 1U), "BLOCK") != 0 &&
                          strcmp(LogFile_TokenGet(tokens, 1U), "BATCH") != 0))
    { return 0U; }
    transfer = LogFile_TokenGet(tokens, 5U);
    if ((strlen(transfer) != 16U) ||
        (LogFile_HexParse(transfer, &request->transfer_high) == 0U) ||
        (LogFile_HexParse(&transfer[8], &request->transfer_low) == 0U) ||
        ((request->transfer_low == 0U) && (request->transfer_high == 0U)) ||
        (LogFile_NumberParse(LogFile_TokenGet(tokens, 4U), &request->offset) == 0U) ||
        (LogFile_NumberParse(LogFile_TokenGet(tokens, 6U), &request->block_sequence) == 0U))
    { return 0U; }
    if ((request->offset > request->size) ||
        (request->block_sequence != request->offset / SYSTEM_LOG_FILE_BLOCK_SIZE))
    { return 0U; }
    request->operation = (strcmp(LogFile_TokenGet(tokens, 1U), "BATCH") == 0) ?
        LOG_FILE_BATCH : LOG_FILE_BLOCK;
    return 1U;
}

static uint8_t LogFile_RequestParse(const LogFileTokens *tokens,
    uint8_t count, LogFileRequest *request)
{
    if ((count < 3U) || (LogFile_NumberParse(LogFile_TokenGet(tokens, 2U), &request->file_id) == 0U))
    { return 0U; }
    if ((strcmp(LogFile_TokenGet(tokens, 1U), "LIST") == 0) && (count == 3U))
    { request->operation = LOG_FILE_LIST; return 1U; }
    if ((request->file_id == 0U) || (request->file_id > SYSTEM_LOG_FILE_ID_MAX))
    { return 0U; }
    if ((strcmp(LogFile_TokenGet(tokens, 1U), "META") == 0) && (count == 3U))
    { request->operation = LOG_FILE_META; return 1U; }
    if (((count != 5U) && (count != 7U)) ||
        (LogFile_TokenParse(LogFile_TokenGet(tokens, 3U), request) == 0U))
    { return 0U; }
    if (count == 7U) { return LogFile_BlockRequestParse(tokens, count, request); }
    if ((strcmp(LogFile_TokenGet(tokens, 1U), "READ") == 0) &&
        (LogFile_NumberParse(LogFile_TokenGet(tokens, 4U), &request->offset) != 0U))
    { request->operation = LOG_FILE_READ; return 1U; }
    if ((strcmp(LogFile_TokenGet(tokens, 1U), "DELETE") == 0) && (strcmp(LogFile_TokenGet(tokens, 4U), "CONFIRM") == 0))
    { request->operation = LOG_FILE_DELETE; return 1U; }
    return 0U;
}

static void LogFile_ErrorWrite(char *response, uint16_t capacity,
    const char *operation, uint32_t id, SystemLogFileResult result)
{
    (void)CommonFormat_Print(response, capacity,
        "ERR LOGFILE %s request_id=%lu code=%s", operation,
        (unsigned long)id, LogFile_ResultText(result));
}

/* Caller holds the mailbox critical section for this bounded snapshot. */
static uint8_t LogFile_ResponseCopyLocked(char *response, uint16_t capacity)
{
    uint16_t length;

    if ((response == NULL) || (capacity == 0U)) { return 0U; }
    for (length = 0U; length < sizeof(s_mailbox.response.text); length++)
    {
        if (s_mailbox.response.text[length] == '\0') { break; }
    }
    SILVERSTAR_ASSERT(length < sizeof(s_mailbox.response.text),
                      SILVERSTAR_ASSERT_MODULE_SYSTEM,
                      SILVERSTAR_ASSERT_REASON_LENGTH_RANGE);
    if (length >= capacity) { return 0U; }
    (void)memcpy(response, s_mailbox.response.text, (size_t)length + 1U);
    return 1U;
}

static void LogFile_Poll(uint32_t id, char *response, uint16_t capacity)
{
    LogFileOperation operation;
    LogFileState mailbox_state;
    uint8_t stale;
    uint8_t copied = 1U;
    uint64_t now_us = SystemTime_GetMonotonicUs();
    PlatformCriticalState state = PlatformCritical_Enter();
    operation = s_mailbox.request.operation;
    mailbox_state = s_mailbox.state;
    stale = (uint8_t)((id != s_mailbox.request.id) || (mailbox_state == LOG_FILE_IDLE));
    if (stale == 0U)
    {
        s_mailbox.last_poll_us = now_us;
        /* Accepted cancellation revokes success immediately; only LoggerTask
         * may replace the old completion after closing the storage handle. */
        if (s_mailbox.cancelled != 0U) { mailbox_state = LOG_FILE_PENDING; }
        if ((mailbox_state == LOG_FILE_DONE) && (operation != LOG_FILE_BATCH))
        {
            if ((operation == LOG_FILE_BLOCK) && (s_mailbox.block_length != 0U) &&
                (s_mailbox.cancelled == 0U))
            { s_binary_request = id; response[0] = '\0'; }
            else { copied = LogFile_ResponseCopyLocked(response, capacity); }
        }
    }
    PlatformCritical_Exit(state);
    if (operation == LOG_FILE_BATCH)
    { LogFile_ErrorWrite(response, capacity, "BATCH", id, SystemLogFileResult_BadArgument); }
    else if (stale != 0U)
    { LogFile_ErrorWrite(response, capacity, "POLL", id, SystemLogFileResult_Stale); }
    else if (copied == 0U)
    { LogFile_ErrorWrite(response, capacity, "POLL", id, SystemLogFileResult_BadArgument); }
    else if (mailbox_state != LOG_FILE_DONE)
    { (void)CommonFormat_Print(response, capacity,
        "PENDING LOGFILE %s request_id=%lu", LogFile_OperationText(operation), (unsigned long)id); }
}

static void LogFile_Submit(LogFileRequest *request, char *response, uint16_t capacity)
{
    SystemLogFileResult result = SystemLogFileResult_Ok;
    uint64_t now_us = SystemTime_GetMonotonicUs();
    PlatformCriticalState state = PlatformCritical_Enter();
    if ((s_mailbox.state == LOG_FILE_PENDING) || (s_mailbox.cancelled != 0U) ||
        (s_mailbox.batch_left != 0U))
    { result = SystemLogFileResult_Busy; }
    else if(s_mailbox.cleanup_failed!=0U)
    {result=SystemLogFileResult_NotReady;}
    else if (s_mailbox.sequence == UINT32_MAX)
    { result = SystemLogFileResult_NotReady; }
    else if(SystemInstallationCapture_OperationBegin(SystemInstallationOperation_LogFile,s_mailbox.lease_owned)!=SYSTEM_DEVICE_OK)
    {result=SystemLogFileResult_Busy;}
    else
    {
        s_mailbox.sequence++;
        s_mailbox.lease_owned=1U;
        request->id = s_mailbox.sequence;
        s_mailbox.request = *request;
        s_mailbox.last_poll_us = now_us;
        s_mailbox.state = LOG_FILE_PENDING;
        s_mailbox.block_length = 0U;
        s_mailbox.batch_left = (request->operation == LOG_FILE_BATCH) ? SYSTEM_LOG_FILE_BATCH_COUNT : 0U;
        s_mailbox.batch_claimed = 0U;
    }
    PlatformCritical_Exit(state);
    if (result != SystemLogFileResult_Ok)
    { LogFile_ErrorWrite(response, capacity, LogFile_OperationText(request->operation), 0U, result); }
    else
    { (void)CommonFormat_Print(response, capacity,
        "PENDING LOGFILE %s request_id=%lu",
        LogFile_OperationText(request->operation), (unsigned long)request->id); }
}

static void LogFile_Control(const LogFileTokens *tokens, uint8_t count,
    char *response, uint16_t capacity)
{
    uint32_t id;
    LogFileRequest request = {0};
    if ((count == 2U) && (strcmp(LogFile_TokenGet(tokens, 1U), "CANCEL") == 0))
    {
        PlatformCriticalState state = PlatformCritical_Enter();
        s_mailbox.cancelled = 1U;
        s_mailbox.batch_left = 0U;
        s_mailbox.batch_claimed = 0U;
        PlatformCritical_Exit(state);
        (void)CommonFormat_Print(response, capacity, "OK LOGFILE CANCEL cancelled=1 cleanup_complete=0");
    }
    else if ((count == 3U) && (strcmp(LogFile_TokenGet(tokens, 1U), "POLL") == 0) &&
        (LogFile_NumberParse(LogFile_TokenGet(tokens, 2U), &id) != 0U))
    { LogFile_Poll(id, response, capacity); }
    else if (LogFile_RequestParse(tokens, count, &request) != 0U)
    {
        if (request.operation == LOG_FILE_DELETE)
        { LogFile_ErrorWrite(response, capacity, "DELETE", 0U, SystemLogFileResult_Unsupported); }
        else { LogFile_Submit(&request, response, capacity); }
    }
    else
    { LogFile_ErrorWrite(response, capacity, "PARSE", 0U, SystemLogFileResult_BadArgument); }
}

static void LogFile_StatusWrite(char *response, uint16_t capacity)
{
    SystemLogFileSnapshot snapshot;
    uint8_t cleanup;
    uint64_t age_ms;
    PlatformCriticalState lock = PlatformCritical_Enter();
    snapshot = s_snapshot;
    cleanup = (uint8_t)((s_mailbox.cancelled!=0U)||(s_mailbox.cleanup_failed!=0U));
    PlatformCritical_Exit(lock);
    if (snapshot.valid == 0U)
    { LogFile_ErrorWrite(response, capacity, "STATUS", 0U, SystemLogFileResult_NotReady); return; }
    age_ms = (SystemTime_GetMonotonicUs() - snapshot.timestamp_us) / 1000ULL;
    (void)CommonFormat_Print(response, capacity,
        "OK LOGFILE STATUS status_version=1 source=FC_DEBUG_RAM sequence=%lu age_ms=%lu lifecycle=%u storage_valid=%u mounted=%u healthy=%u writer_open=%u log_fault=%u finalization=%u maintenance=%u cleanup_pending=%u reboot_required=%u",
        (unsigned long)snapshot.sequence, (unsigned long)((age_ms > UINT32_MAX) ? UINT32_MAX : age_ms),
        (unsigned int)snapshot.lifecycle, (unsigned int)snapshot.storage_valid,
        (unsigned int)snapshot.mounted, (unsigned int)snapshot.healthy,
        (unsigned int)snapshot.writer_open, (unsigned int)snapshot.log_fault,
        (unsigned int)snapshot.finalization, (unsigned int)SystemLifecycle_MaintenanceGet(),
        (unsigned int)cleanup, (unsigned int)(SystemLifecycle_MaintenanceGet() != SystemMaintenanceState_Off));
}

static void LogFile_MaintenanceEnter(char *response, uint16_t capacity)
{
    SystemDeviceResult result = SystemLifecycle_MaintenanceRequest();
    if (result != SYSTEM_DEVICE_OK)
    { LogFile_ErrorWrite(response, capacity, "ENTER", 0U,
        (result == SYSTEM_DEVICE_BUSY) ? SystemLogFileResult_Busy : SystemLogFileResult_Locked); }
    else
    { (void)CommonFormat_Print(response, capacity,
        "OK LOGFILE ENTER accepted=1 maintenance=%u reboot_required=1",
        (unsigned int)SystemLifecycle_MaintenanceGet()); }
}

SystemConsoleExecuteResult SystemLogFile_ExecuteLine(
    const char *line, char *response, uint16_t capacity)
{
    LogFileTokens tokens = {0};
    uint16_t length;
    uint8_t count;
    s_binary_request = 0U;
    if ((response == NULL) || (capacity == 0U))
    { return SYSTEM_CONSOLE_EXECUTE_BAD_ARGUMENT; }
    response[0] = '\0';
    if ((line == NULL) || (capacity < SYSTEM_LOG_FILE_RESPONSE_SIZE))
    { return SYSTEM_CONSOLE_EXECUTE_BAD_ARGUMENT; }
    for (length = 0U; length < sizeof(tokens.text); length++)
    {
        tokens.text[length] = line[length];
        if (line[length] == '\0') { break; }
    }
    count = (length < sizeof(tokens.text)) ? LogFile_Tokenize(&tokens) : 0U;
    if ((count < 2U) || (strcmp(LogFile_TokenGet(&tokens, 0U), "LOGFILE") != 0))
    { LogFile_ErrorWrite(response, capacity, "PARSE", 0U, SystemLogFileResult_BadArgument); }
    else if ((count == 2U) && (strcmp(LogFile_TokenGet(&tokens, 1U), "CAPS") == 0))
    { (void)CommonFormat_Print(response, capacity,
        "OK LOGFILE CAPS file_service_version=1 supported=%u max_chunk=64 delete_supported=0 telemetry_bulk=0 device_id=unknown boot_id=unknown status_version=1 maintenance_required=1 block_version=1 max_block=512 block_encoding=COBS block_window=1 batch_version=1 batch_count=4 firmware=" SILVERSTAR_VERSION_STRING SILVERSTAR_BUILD_IDENTITY_FIELDS SILVERSTAR_MAINTENANCE_UART_FIELDS,
        (unsigned int)(SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)); }
    else if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED == 0U)
    { LogFile_ErrorWrite(response, capacity, "PARSE", 0U, SystemLogFileResult_Unsupported); }
    else if ((count == 2U) && (strcmp(LogFile_TokenGet(&tokens, 1U), "STATUS") == 0))
    { LogFile_StatusWrite(response, capacity); }
    else if ((count == 2U) && (strcmp(LogFile_TokenGet(&tokens, 1U), "ENTER") == 0))
    { LogFile_MaintenanceEnter(response, capacity); }
    else { LogFile_Control(&tokens, count, response, capacity); }
    return SYSTEM_CONSOLE_EXECUTE_OK;
}

static const uint32_t s_crc_nibble[16] = {
    0x00000000U, 0x1DB71064U, 0x3B6E20C8U, 0x26D930ACU,
    0x76DC4190U, 0x6B6B51F4U, 0x4DB26158U, 0x5005713CU,
    0xEDB88320U, 0xF00F9344U, 0xD6D6A3E8U, 0xCB61B38CU,
    0x9B64C2B0U, 0x86D3D2D4U, 0xA00AE278U, 0xBDBDF21CU
};

static uint32_t LogFile_CrcUpdate(uint32_t crc, const uint8_t *data, uint16_t length)
{
    uint16_t index;
    SILVERSTAR_ASSERT(length <= SYSTEM_LOG_FILE_HASH_QUANTUM,
        SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_LENGTH_RANGE);
    for (index = 0U; index < length; index++)
    {
        crc ^= data[index];
        crc = (crc >> 4U) ^ s_crc_nibble[crc & 0x0FU];
        crc = (crc >> 4U) ^ s_crc_nibble[crc & 0x0FU];
    }
    return crc;
}

static void LogFile_BlockPut32(uint16_t offset, uint32_t value)
{
    uint8_t index;
    SILVERSTAR_ASSERT(offset <= LOG_FILE_BLOCK_RAW_SIZE - 4U,
        SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
    for (index = 0U; index < 4U; index++)
    { s_scratch.block[offset + index] = (uint8_t)(value >> (index * 8U)); }
}

static void LogFile_BlockHeaderWrite(const LogFileRequest *request, uint16_t length)
{
    SILVERSTAR_ASSERT((request->offset <= request->size) &&
        (length <= request->size - request->offset) && (length <= SYSTEM_LOG_FILE_BLOCK_SIZE),
        SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_LENGTH_RANGE);
    (void)memset(s_scratch.block, 0, LOG_FILE_BLOCK_HEADER_SIZE);
    (void)memcpy(s_scratch.block, "SLB1", 4U);
    s_scratch.block[4] = 1U; s_scratch.block[5] = 1U;
    s_scratch.block[6] = (uint8_t)(length == request->size - request->offset);
    LogFile_BlockPut32(8U, request->transfer_low);
    LogFile_BlockPut32(12U, request->transfer_high);
    LogFile_BlockPut32(16U, request->id);
    LogFile_BlockPut32(20U, request->block_sequence);
    LogFile_BlockPut32(24U, request->file_id);
    LogFile_BlockPut32(28U, request->crc);
    LogFile_BlockPut32(32U, request->size);
    LogFile_BlockPut32(36U, request->offset);
    s_scratch.block[40] = (uint8_t)length;
    s_scratch.block[41] = (uint8_t)(length >> 8U);
}

static uint16_t LogFile_BlockEncode(uint8_t *data, uint16_t length)
{
    uint16_t index;
    uint16_t code_at = 1U;
    uint16_t written = 2U;
    uint8_t code = 1U;
    SILVERSTAR_ASSERT((length >= LOG_FILE_BLOCK_HEADER_SIZE + 4U) &&
        (length <= LOG_FILE_BLOCK_RAW_SIZE), SILVERSTAR_ASSERT_MODULE_SYSTEM,
        SILVERSTAR_ASSERT_REASON_LENGTH_RANGE);
    data[0] = 0U;
    for (index = 0U; index < LOG_FILE_BLOCK_RAW_SIZE; index++)
    {
        if (index >= length) { break; }
        uint8_t value;
        SILVERSTAR_ASSERT((code_at < written) && (written <= index + 4U) &&
            (written < SYSTEM_LOG_FILE_BLOCK_WIRE_SIZE - 1U),
            SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_BUFFER_CAPACITY);
        /* Raw input starts four bytes ahead; max two extra run codes for560
         * bytes. Read before writing so forward encoding cannot eat input. */
        value = data[index + 4U];
        if (value == 0U)
        { data[code_at] = code; code_at = written++; code = 1U; }
        else
        {
            data[written++] = value; code++;
            if (code == 255U)
            { data[code_at] = code; code_at = written++; code = 1U; }
        }
    }
    SILVERSTAR_ASSERT((code_at < written) && (written < SYSTEM_LOG_FILE_BLOCK_WIRE_SIZE),
        SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_BUFFER_CAPACITY);
    data[code_at] = code;
    data[written++] = 0U;
    return written;
}

SystemLogFileResult SystemLogFile_BinaryResponseGet(
    uint8_t *data, uint16_t capacity, uint16_t *length)
{
    SystemLogFileResult result = SystemLogFileResult_NotReady;
    uint16_t raw_length = 0U;
    PlatformCriticalState state;
    if ((data == NULL) || (length == NULL)) { return SystemLogFileResult_BadArgument; }
    *length = 0U;
    state = PlatformCritical_Enter();
    if (s_binary_request != 0U)
    {
        result = SystemLogFileResult_Stale;
        if ((s_mailbox.state == LOG_FILE_DONE) && (s_mailbox.cancelled == 0U) &&
            (s_mailbox.request.id == s_binary_request) &&
            (s_mailbox.request.operation == LOG_FILE_BLOCK) && (s_mailbox.block_length != 0U))
        {
            raw_length = s_mailbox.block_length;
            SILVERSTAR_ASSERT((raw_length >= LOG_FILE_BLOCK_HEADER_SIZE + 4U) &&
                (raw_length <= LOG_FILE_BLOCK_RAW_SIZE), SILVERSTAR_ASSERT_MODULE_SYSTEM,
                SILVERSTAR_ASSERT_REASON_LENGTH_RANGE);
            result = SystemLogFileResult_BadArgument;
            if (capacity >= SYSTEM_LOG_FILE_BLOCK_WIRE_SIZE)
            {
                (void)memcpy(&data[4], s_mailbox.response.block, raw_length);
                result = SystemLogFileResult_Ok;
            }
        }
        s_binary_request = 0U;
    }
    PlatformCritical_Exit(state);
    if (result == SystemLogFileResult_Ok) { *length = LogFile_BlockEncode(data, raw_length); }
    return result;
}

/* SerialTask reserves one ready record, then reports whole-frame TX admission.
 * LoggerTask cannot reuse the mailbox until admission succeeds. No TF here. */
SystemLogFileResult SystemLogFile_BatchResponseGet(
    uint8_t *data, uint16_t capacity, uint16_t *length)
{
    uint16_t raw_length = 0U;
    PlatformCriticalState state;
    if ((data == NULL) || (length == NULL)) { return SystemLogFileResult_BadArgument; }
    *length = 0U;
    if (capacity < SYSTEM_LOG_FILE_BLOCK_WIRE_SIZE) { return SystemLogFileResult_BadArgument; }
    state = PlatformCritical_Enter();
    SILVERSTAR_ASSERT(s_mailbox.batch_left <= SYSTEM_LOG_FILE_BATCH_COUNT,
        SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    if ((s_mailbox.request.operation != LOG_FILE_BATCH) || (s_mailbox.batch_left == 0U) ||
        (s_mailbox.state != LOG_FILE_DONE) || (s_mailbox.cancelled != 0U) ||
        (s_mailbox.batch_claimed != 0U))
    { PlatformCritical_Exit(state); return SystemLogFileResult_NotReady; }
    raw_length = s_mailbox.block_length;
    SILVERSTAR_ASSERT((raw_length == 0U) || ((raw_length >= LOG_FILE_BLOCK_HEADER_SIZE + 4U) &&
        (raw_length <= LOG_FILE_BLOCK_RAW_SIZE)), SILVERSTAR_ASSERT_MODULE_SYSTEM,
        SILVERSTAR_ASSERT_REASON_LENGTH_RANGE);
    if (raw_length != 0U) { (void)memcpy(&data[4], s_mailbox.response.block, raw_length); }
    else if (LogFile_ResponseCopyLocked((char *)data, capacity) == 0U)
    { PlatformCritical_Exit(state); return SystemLogFileResult_BadArgument; }
    s_mailbox.batch_claimed = 1U;
    PlatformCritical_Exit(state);
    if (raw_length != 0U) { *length = LogFile_BlockEncode(data, raw_length); }
    else
    {
        uint16_t text_length = (uint16_t)strlen((const char *)data);
        data[text_length++] = '\r'; data[text_length++] = '\n'; *length = text_length;
    }
    return SystemLogFileResult_Ok;
}

void SystemLogFile_BatchResponseSent(uint8_t accepted)
{
    uint16_t payload;
    PlatformCriticalState state = PlatformCritical_Enter();
    SILVERSTAR_ASSERT((accepted <= 1U) && (s_mailbox.batch_left <= SYSTEM_LOG_FILE_BATCH_COUNT),
        SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    if ((s_mailbox.batch_claimed != 0U) && (s_mailbox.batch_left != 0U) &&
        (s_mailbox.cancelled == 0U) && (accepted != 0U))
    {
        if (s_mailbox.block_length == 0U) { s_mailbox.batch_left = 0U; }
        else
        {
            payload = (uint16_t)(s_mailbox.block_length - LOG_FILE_BLOCK_HEADER_SIZE - 4U);
            SILVERSTAR_ASSERT((s_mailbox.request.offset <= s_mailbox.request.size) &&
                (payload <= SYSTEM_LOG_FILE_BLOCK_SIZE) &&
                (payload <= s_mailbox.request.size - s_mailbox.request.offset),
                SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_LENGTH_RANGE);
            s_mailbox.batch_left--;
            s_mailbox.request.offset += payload;
            if (s_mailbox.request.offset == s_mailbox.request.size) { s_mailbox.batch_left = 0U; }
            if (s_mailbox.batch_left != 0U)
            {
                s_mailbox.request.block_sequence++;
                s_mailbox.block_length = 0U;
                s_mailbox.state = LOG_FILE_PENDING;
            }
        }
    }
    s_mailbox.batch_claimed = 0U;
    PlatformCritical_Exit(state);
}

static SystemLogFileResult LogFile_BlockRead(const LogFileRequest *request)
{
    uint16_t length = 0U;
    uint16_t expected;
    uint32_t crc;
    SystemLogFileResult result;
    if ((s_worker.cached == 0U) || (request->file_id != s_worker.file_id) ||
        (request->size != s_worker.size) || (request->crc != s_worker.crc))
    { return SystemLogFileResult_Stale; }
    if (request->offset > request->size) { return SystemLogFileResult_BadArgument; }
    expected = (request->size - request->offset > SYSTEM_LOG_FILE_BLOCK_SIZE) ?
        SYSTEM_LOG_FILE_BLOCK_SIZE : (uint16_t)(request->size - request->offset);
    result = SystemLogFileStorage_BlockRead(request->file_id, request->size,
        request->offset, &s_scratch.block[LOG_FILE_BLOCK_HEADER_SIZE], &length);
    if (result != SystemLogFileResult_Ok) { return result; }
    SILVERSTAR_ASSERT(length == expected, SILVERSTAR_ASSERT_MODULE_SYSTEM,
        SILVERSTAR_ASSERT_REASON_LENGTH_RANGE);
    LogFile_BlockHeaderWrite(request, length);
    crc = LogFile_CrcUpdate(UINT32_MAX, s_scratch.block, LOG_FILE_BLOCK_HEADER_SIZE);
    crc = ~LogFile_CrcUpdate(crc, &s_scratch.block[LOG_FILE_BLOCK_HEADER_SIZE], length);
    LogFile_BlockPut32((uint16_t)(LOG_FILE_BLOCK_HEADER_SIZE + length), crc);
    return SystemLogFileResult_Ok;
}

static void LogFile_MetadataWrite(const LogFileRequest *request)
{
    (void)CommonFormat_Print(s_scratch.result, sizeof(s_scratch.result),
        "OK LOGFILE META request_id=%lu file_id=%lu token=1-%08lX-%08lX size=%lu crc32=%08lX format=SSLOG format_version=0.0 closed=1",
        (unsigned long)request->id, (unsigned long)request->file_id,
        (unsigned long)s_worker.crc, (unsigned long)s_worker.size,
        (unsigned long)s_worker.size, (unsigned long)s_worker.crc);
}

static SystemLogFileResult LogFile_HashFinish(const LogFileRequest *request)
{
    SystemLogFileResult result = SystemLogFileStorage_Reset();
    s_worker.hashing = 0U;
    if (result != SystemLogFileResult_Ok) { return result; }
    if (s_worker.count != s_worker.size) { return SystemLogFileResult_Stale; }
    s_worker.crc = ~s_worker.crc;
    s_worker.cached = 1U;
    LogFile_MetadataWrite(request);
    return SystemLogFileResult_Ok;
}

static SystemLogFileResult LogFile_HashProcess(const LogFileRequest *request)
{
    uint16_t length = 0U;
    SystemLogFileResult result;
    if (s_worker.hashing == 0U)
    {
        s_worker.cached = 0U;
        result = SystemLogFileStorage_Reset();
        if (result != SystemLogFileResult_Ok) { return result; }
        result = SystemLogFileStorage_HashBegin(request->file_id, &s_worker.size);
        if (result != SystemLogFileResult_Ok) { return result; }
        s_worker.hashing = 1U;
        s_worker.file_id = request->file_id;
        s_worker.crc = UINT32_MAX;
        s_worker.count = 0U;
        return SystemLogFileResult_Pending;
    }
    result = SystemLogFileStorage_HashRead(s_scratch.data, &length);
    if (result != SystemLogFileResult_Ok) { return result; }
    if ((s_worker.count > s_worker.size) ||
        (length > s_worker.size - s_worker.count)) { return SystemLogFileResult_Stale; }
    s_worker.crc = LogFile_CrcUpdate(s_worker.crc, s_scratch.data, length);
    s_worker.count += length;
    if (length == 0U) { return LogFile_HashFinish(request); }
    return SystemLogFileResult_Pending;
}

static SystemLogFileResult LogFile_Read(const LogFileRequest *request)
{
    static const char hex[] = "0123456789ABCDEF";
    char data[SYSTEM_LOG_FILE_CHUNK_SIZE * 2U + 1U];
    uint16_t length = 0U;
    uint16_t index;
    uint32_t crc;
    SystemLogFileResult result;
    if ((s_worker.cached == 0U) || (request->file_id != s_worker.file_id) ||
        (request->size != s_worker.size) || (request->crc != s_worker.crc))
    { return SystemLogFileResult_Stale; }
    if (request->offset > request->size) { return SystemLogFileResult_BadArgument; }
    result = SystemLogFileStorage_Read(request->file_id, request->size,
        request->offset, s_scratch.data, &length);
    if (result != SystemLogFileResult_Ok) { return result; }
    SILVERSTAR_ASSERT(length <= SYSTEM_LOG_FILE_CHUNK_SIZE,
        SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_LENGTH_RANGE);
    for (index = 0U; index < length; index++)
    { data[index * 2U] = hex[s_scratch.data[index] >> 4U]; data[index * 2U + 1U] = hex[s_scratch.data[index] & 15U]; }
    data[length * 2U] = '\0';
    if (length == 0U) { data[0] = '-'; data[1] = '\0'; }
    crc = ~LogFile_CrcUpdate(UINT32_MAX, s_scratch.data, length);
    (void)CommonFormat_Print(s_scratch.result, sizeof(s_scratch.result),
        "OK LOGFILE READ request_id=%lu file_id=%lu token=1-%08lX-%08lX offset=%lu length=%u crc32=%08lX data=%s",
        (unsigned long)request->id, (unsigned long)request->file_id,
        (unsigned long)request->crc, (unsigned long)request->size,
        (unsigned long)request->offset, (unsigned int)length, (unsigned long)crc, data);
    return SystemLogFileResult_Ok;
}

static SystemLogFileResult LogFile_List(const LogFileRequest *request)
{
    uint32_t file_id = 0U;
    uint32_t size = 0U;
    uint32_t next_cursor = 0U;
    SystemLogFileResult result = SystemLogFileStorage_List(
        s_worker.cursor, &next_cursor, &file_id, &size);
    s_worker.cursor = next_cursor;
    if (result != SystemLogFileResult_Ok) { return result; }
    if (file_id == 0U)
    { (void)CommonFormat_Print(s_scratch.result, sizeof(s_scratch.result),
        "OK LOGFILE LIST request_id=%lu end=1 next_cursor=0", (unsigned long)request->id); }
    else
    { (void)CommonFormat_Print(s_scratch.result, sizeof(s_scratch.result),
        "OK LOGFILE LIST request_id=%lu file_id=%lu size=%lu closed=1 next_cursor=%lu end=0",
        (unsigned long)request->id, (unsigned long)file_id,
        (unsigned long)size, (unsigned long)next_cursor); }
    return SystemLogFileResult_Ok;
}

static SystemLogFileResult LogFile_Work(const LogFileRequest *request)
{
    SystemLogFileResult result = SystemLogFileStorage_Check(
        (request->operation == LOG_FILE_LIST) ? 0U : request->file_id,
        (uint8_t)(request->operation == LOG_FILE_DELETE));
    if (result != SystemLogFileResult_Ok) { return result; }
    if (request->operation == LOG_FILE_LIST) { return LogFile_List(request); }
    if (request->operation == LOG_FILE_READ) { return LogFile_Read(request); }
    if ((request->operation == LOG_FILE_BLOCK) || (request->operation == LOG_FILE_BATCH))
    { return LogFile_BlockRead(request); }
    return LogFile_HashProcess(request);
}

static void LogFile_Abort(const LogFileRequest *request, SystemLogFileResult result)
{
    SystemLogFileResult closed = SystemLogFileStorage_Reset();
    PlatformCriticalState state;
    s_worker.hashing = 0U;
    s_worker.cached = 0U;
    if (closed != SystemLogFileResult_Ok)
    {
        result = closed;
        if (SystemLifecycle_MaintenanceGet() != SystemMaintenanceState_Off)
        { SystemLifecycle_MaintenanceComplete(0U); }
    }
    LogFile_ErrorWrite(s_scratch.result, sizeof(s_scratch.result),
        LogFile_OperationText(request->operation), request->id, result);
    state = PlatformCritical_Enter();
    SILVERSTAR_ASSERT(s_mailbox.request.id == request->id,
        SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_SEQUENCE_INVARIANT);
    (void)memcpy(s_mailbox.response.text, s_scratch.result, sizeof(s_mailbox.response.text));
    s_mailbox.block_length = 0U;
    s_mailbox.batch_claimed = 0U;
    s_mailbox.state = (request->id == 0U) ? LOG_FILE_IDLE : LOG_FILE_DONE;
    s_mailbox.last_poll_us = SystemTime_GetMonotonicUs();
    s_mailbox.cancelled = 0U;
    /* Reset/close and cache revocation completed before releasing TF use.
     * An uncertain close keeps the reservation until reboot. */
    if((SYSTEM_INSTALLATION_CAPTURE_ENABLED!=0U)&&(closed!=SystemLogFileResult_Ok))
    {s_mailbox.cleanup_failed=1U;}
    if(closed==SystemLogFileResult_Ok&&s_mailbox.cleanup_failed==0U&&s_mailbox.lease_owned!=0U)
    {
        SystemInstallationCapture_OperationEnd(SystemInstallationOperation_LogFile);
        s_mailbox.lease_owned=0U;
    }
    PlatformCritical_Exit(state);
}

static void LogFile_Complete(const LogFileRequest *request, SystemLogFileResult result)
{
    PlatformCriticalState state = PlatformCritical_Enter();
    SILVERSTAR_ASSERT((s_mailbox.request.id == request->id) &&
        (s_mailbox.state == LOG_FILE_PENDING), SILVERSTAR_ASSERT_MODULE_SYSTEM,
        SILVERSTAR_ASSERT_REASON_SEQUENCE_INVARIANT);
    if (s_mailbox.cancelled != 0U) { result = SystemLogFileResult_Cancelled; }
    if (result == SystemLogFileResult_Ok)
    {
        if ((request->operation != LOG_FILE_BLOCK) && (request->operation != LOG_FILE_BATCH))
        { (void)memcpy(s_mailbox.response.text, s_scratch.result, sizeof(s_mailbox.response.text)); }
        else
        {
            uint16_t length = (uint16_t)((uint16_t)s_scratch.block[40] |
                (uint16_t)((uint16_t)s_scratch.block[41] << 8U));
            SILVERSTAR_ASSERT(length <= SYSTEM_LOG_FILE_BLOCK_SIZE, SILVERSTAR_ASSERT_MODULE_SYSTEM,
                SILVERSTAR_ASSERT_REASON_LENGTH_RANGE);
            s_mailbox.block_length = (uint16_t)(LOG_FILE_BLOCK_HEADER_SIZE + length + 4U);
            (void)memcpy(s_mailbox.response.block, s_scratch.block, s_mailbox.block_length);
        }
        s_mailbox.state = LOG_FILE_DONE;
        PlatformCritical_Exit(state);
        return;
    }
    /* Reserve the mailbox until the owner closes handles and revokes cache. */
    s_mailbox.cancelled = 1U;
    PlatformCritical_Exit(state);
    LogFile_Abort(request, result);
}

static uint8_t LogFile_ProcessQuantum(uint8_t session_finalized)
{
    LogFileRequest request;
    SystemLogFileResult result;
    uint8_t cancelled;
    uint8_t timed_out;
    LogFileState mailbox_state;
    PlatformCriticalState state = PlatformCritical_Enter();
    request = s_mailbox.request;
    mailbox_state = s_mailbox.state;
    cancelled = s_mailbox.cancelled;
    timed_out = (uint8_t)((mailbox_state != LOG_FILE_IDLE) &&
        ((SystemTime_GetMonotonicUs() - s_mailbox.last_poll_us) >= LOG_FILE_IDLE_TIMEOUT_US));
    if ((cancelled != 0U) || (timed_out != 0U)) { s_mailbox.cancelled = 1U; }
    PlatformCritical_Exit(state);
    SILVERSTAR_ASSERT(mailbox_state <= LOG_FILE_DONE,
        SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    if ((cancelled != 0U) || (timed_out != 0U))
    {
        LogFile_Abort(&request, (cancelled != 0U) ?
            SystemLogFileResult_Cancelled : SystemLogFileResult_Timeout);
        return 0U;
    }
    if (mailbox_state != LOG_FILE_PENDING) { return 0U; }
    SILVERSTAR_ASSERT((request.id != 0U) && (request.operation <= LOG_FILE_BATCH),
        SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    SILVERSTAR_ASSERT(session_finalized <= 1U,
        SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    SILVERSTAR_ASSERT((s_worker.hashing <= 1U) && (s_worker.cached <= 1U) &&
        !((s_worker.hashing != 0U) && (s_worker.cached != 0U)),
        SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    if (s_worker.request_id != request.id)
    { s_worker.request_id = request.id; s_worker.cursor = request.file_id; }
    result = (session_finalized != 0U) ? LogFile_Work(&request) : SystemLogFileResult_Locked;
    if (result != SystemLogFileResult_Pending)
    { LogFile_Complete(&request, result); return 0U; }
    return (uint8_t)(request.operation == LOG_FILE_META);
}

void SystemLogFile_Process(uint8_t session_finalized)
{
    uint8_t quantum;
    uint64_t started_us = SystemTime_GetMonotonicUs();
    for (quantum = 0U; quantum < LOG_FILE_META_QUANTA; quantum++)
    {
        if ((quantum != 0U) &&
            (SystemTime_GetMonotonicUs() - started_us >= LOG_FILE_SERVICE_BUDGET_US))
        { return; }
        /* Re-snapshot cancel, timeout, lifecycle and lease before each quantum. */
        if (LogFile_ProcessQuantum(session_finalized) == 0U) { return; }
    }
}

uint8_t SystemLogFile_IsActive(void)
{
    uint8_t pending;
    PlatformCriticalState state = PlatformCritical_Enter();
    pending = (uint8_t)((s_mailbox.state == LOG_FILE_PENDING) ||
        (s_mailbox.cancelled != 0U));
    PlatformCritical_Exit(state);
    /* The worker state is private to this LoggerTask caller. */
    return (uint8_t)((pending != 0U) || (s_worker.hashing != 0U) || (s_worker.cached != 0U));
}
