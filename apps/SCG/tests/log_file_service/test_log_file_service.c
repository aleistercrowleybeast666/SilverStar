/* Synthetic filesystem/lifecycle interleavings, never a target or TF test. */
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "system_log_file.h"
#include "system_storage_if.h"
#include "system_lifecycle.h"
#include "platform_critical.h"
#include "silverstar_assert.h"
#include "project_storage_binding.h"

static uint64_t s_now;
static uint32_t s_current = 2U;
static SystemLifecycleState s_lifecycle = SYSTEM_STATE_PREFLIGHT;
static uint32_t s_io_count;
static uint32_t s_critical_depth;
static uint8_t s_close_error;
static uint8_t s_read_error;
static uint8_t s_cancel_in_read;
static uint8_t s_submit_in_close;
static uint8_t s_submit_busy;
static uint8_t s_size_change;
static uint8_t s_cancel_on_close;
static uint8_t s_cancel_at_enter;
static char s_reply[512];

static void Execute(const char *text)
{
    assert(SystemLogFile_ExecuteLine(text, s_reply, sizeof(s_reply)) == SYSTEM_CONSOLE_EXECUTE_OK);
}
static unsigned int Submit(const char *text)
{
    unsigned int id = 0U;
    const char *start;
    uint32_t before = s_io_count;
    Execute(text);
    assert(s_io_count == before);
    assert(strncmp(s_reply, "PENDING ", 8U) == 0);
    start = strstr(s_reply, "request_id=");
    assert(start != NULL && sscanf(start, "request_id=%u", &id) == 1);
    return id;
}
static void Poll(unsigned int id)
{
    char text[64];
    assert(snprintf(text, sizeof(text), "LOGFILE POLL %u", id) > 0);
    Execute(text);
}
static void Finish(unsigned int id)
{
    unsigned int step;
    for (step = 0U; step < 30U; step++)
    {
        SystemLogFile_Process();
        Poll(id);
        if (strncmp(s_reply, "PENDING ", 8U) != 0) { return; }
    }
    assert(0 && "bounded fixture did not complete");
}
PlatformCriticalState PlatformCritical_Enter(void)
{
    if (s_cancel_at_enter) { s_cancel_at_enter = 0U; Execute("LOGFILE CANCEL"); }
    return s_critical_depth++;
}
void PlatformCritical_Exit(PlatformCriticalState state) { assert(s_critical_depth == state + 1U); s_critical_depth = state; }
uint64_t SystemTime_GetMonotonicUs(void) { return s_now; }
SystemLifecycleState SystemLifecycle_GetState(void) { return s_lifecycle; }
SystemDeviceResult SystemStorage_HealthGet(SystemStorageHealth *health)
{ memset(health, 0, sizeof(*health)); health->mounted = 1U; health->healthy = 1U; health->file_open = 1U; return SYSTEM_DEVICE_OK; }
SystemDeviceResult SystemStorage_MissionIdGet(uint32_t *id) { *id = s_current; return SYSTEM_DEVICE_OK; }
void SilverStarAssert_Check(uint8_t condition, SilverStarAssertModuleId module,
    const char *file, uint32_t line, SilverStarAssertReasonId reason)
{ (void)module; (void)reason; if (!condition) { fprintf(stderr, "%s:%u assertion\n", file, line); abort(); } }
void SilverStarAssert_ObjectCheck(const volatile void *object, uint32_t alignment,
    SilverStarAssertModuleId module, const char *file, uint32_t line)
{ (void)module; (void)file; (void)line; assert(object != NULL && (uintptr_t)object % alignment == 0U); }
static void Io(void) { assert(s_critical_depth == 0U); s_io_count++; }
FRESULT f_open(FIL *file, const char *path, BYTE mode)
{
    Io(); assert(mode == FA_READ);
    if (strcmp(path, "0:/missions/000001/flight.sslog") != 0) { return FR_NO_FILE; }
    file->offset = 0U; file->size = s_size_change ? 10U : 9U; file->id = 1U; return FR_OK;
}
FRESULT f_close(FIL *file)
{
    (void)file; Io();
    if (s_submit_in_close) { s_submit_in_close = 0U; Execute("LOGFILE META 1"); s_submit_busy = (strstr(s_reply, "code=BUSY") != NULL); }
    if (s_cancel_on_close) { s_cancel_on_close = 0U; s_cancel_at_enter = 1U; }
    return s_close_error ? FR_DISK_ERR : FR_OK;
}
FRESULT f_read(FIL *file, void *data, UINT capacity, UINT *count)
{
    static const char bytes[] = "123456789X";
    Io();
    if (s_cancel_in_read) { s_cancel_in_read = 0U; Execute("LOGFILE CANCEL"); }
    if (s_read_error) { *count = 0U; return FR_DISK_ERR; }
    *count = file->size - file->offset;
    if (*count > capacity) { *count = capacity; }
    memcpy(data, bytes + file->offset, *count); file->offset += *count; return FR_OK;
}
FRESULT f_lseek(FIL *file, uint32_t offset) { Io(); file->offset = offset; return FR_OK; }
FRESULT f_stat(const char *path, FILINFO *info)
{ Io(); if (strcmp(path, "0:/missions/000001/flight.sslog") != 0) { return FR_NO_FILE; } info->fattrib = 0U; info->fsize = 9U; return FR_OK; }
FRESULT f_opendir(DIR *directory, const char *path)
{ Io(); assert(strcmp(path, "0:/missions") == 0); directory->index = 0U; return FR_OK; }
FRESULT f_readdir(DIR *directory, FILINFO *info)
{
    static const char *names[] = {"garbage", "000002", "000001", "000003", ""};
    Io(); assert(directory->index < 5U); strcpy(info->fname, names[directory->index++]); info->fattrib = AM_DIR; return FR_OK;
}
FRESULT f_closedir(DIR *directory) { (void)directory; Io(); return s_close_error ? FR_DISK_ERR : FR_OK; }

static void Normal(void)
{
    unsigned int id;
    Execute("LOGFILE CAPS"); assert(strstr(s_reply, "delete_supported=0") && strstr(s_reply, "boot_id=unknown"));
    Execute("LOGFILE DELETE 1 1-CBF43926-00000009 CONFIRM"); assert(strstr(s_reply, "code=UNSUPPORTED")); assert(s_io_count == 0U);
    Execute("LOGFILE META ../x"); assert(strstr(s_reply, "code=BAD_ARGUMENT"));
    Execute("LOGFILE META 4294967296"); assert(strstr(s_reply, "code=BAD_ARGUMENT"));
    Execute("LOGFILE READ 1 bad 0 extra"); assert(strstr(s_reply, "code=BAD_ARGUMENT"));
    id = Submit("LOGFILE LIST 0"); Finish(id); assert(strstr(s_reply, "file_id=1") && strstr(s_reply, "next_cursor=3"));
    id = Submit("LOGFILE LIST 3"); Finish(id); assert(strstr(s_reply, "end=1"));
    id = Submit("LOGFILE META 2"); Finish(id); assert(strstr(s_reply, "code=LOCKED"));
    id = Submit("LOGFILE META 1"); Execute("LOGFILE META 1"); assert(strstr(s_reply, "code=BUSY")); Finish(id);
    assert(strstr(s_reply, "token=1-CBF43926-00000009") && strstr(s_reply, "format_version=0.0"));
    id = Submit("LOGFILE READ 1 1-CBF43926-00000009 0"); Finish(id);
    assert(strstr(s_reply, "crc32=CBF43926 data=313233343536373839"));
    id = Submit("LOGFILE READ 1 1-CBF43926-00000009 9"); Finish(id); assert(strstr(s_reply, "length=0 crc32=00000000 data=-"));
    s_size_change = 1U; id = Submit("LOGFILE READ 1 1-CBF43926-00000009 0"); Finish(id); assert(strstr(s_reply, "code=STALE")); s_size_change = 0U;
    id = Submit("LOGFILE META 1"); s_lifecycle = SYSTEM_STATE_FLIGHT; Finish(id); assert(strstr(s_reply, "code=LOCKED")); s_lifecycle = SYSTEM_STATE_PREFLIGHT;
    id = Submit("LOGFILE META 1"); Finish(id); assert(strstr(s_reply, "OK LOGFILE META"));
    Execute("LOGFILE CANCEL"); SystemLogFile_Process();
    id = Submit("LOGFILE READ 1 1-CBF43926-00000009 0"); Finish(id); assert(strstr(s_reply, "code=STALE"));
    id = Submit("LOGFILE META 1"); SystemLogFile_Process(); s_cancel_in_read = 1U; SystemLogFile_Process(); SystemLogFile_Process(); Poll(id); assert(strstr(s_reply, "code=CANCELLED"));
    id = Submit("LOGFILE META 1"); SystemLogFile_Process(); s_now += 30000001ULL; s_submit_in_close = 1U; SystemLogFile_Process(); Poll(id); assert(strstr(s_reply, "code=TIMEOUT")); assert(s_submit_busy);
    id = Submit("LOGFILE READ 1 1-CBF43926-00000009 0"); Finish(id); assert(strstr(s_reply, "code=STALE"));
    id = Submit("LOGFILE META 1"); s_cancel_on_close = 1U; Finish(id); assert(strstr(s_reply, "code=CANCELLED"));
    id = Submit("LOGFILE READ 1 1-CBF43926-00000009 0"); Finish(id); assert(strstr(s_reply, "code=STALE"));
    id = Submit("LOGFILE META 1");
    for (unsigned int step = 0U; step < 4U; step++) { s_now += 20000000ULL; Poll(id); SystemLogFile_Process(); }
    Poll(id); assert(strstr(s_reply, "OK LOGFILE META"));
    id = Submit("LOGFILE META 1"); s_read_error = 1U; Finish(id); assert(strstr(s_reply, "code=IO_ERROR")); s_read_error = 0U;
    id = Submit("LOGFILE META 1"); Finish(id); assert(strstr(s_reply, "OK LOGFILE META"));
    printf("PASS log file service normal, path/overflow, active mission, flight lock, CRC/EOF/stale, cancel, timeout, owner interleaving, I/O fault\n");
}
int main(int argc, char *argv[])
{
    if ((argc > 1) && strcmp(argv[1], "disabled") == 0)
    {
        Execute("LOGFILE CAPS"); assert(strstr(s_reply, "supported=0 max_chunk"));
        Execute("LOGFILE META 1"); assert(strstr(s_reply, "code=UNSUPPORTED"));
        SystemLogFile_Process(); assert(s_io_count == 0U);
        puts("PASS logging disabled: linked at O0, capability false and no filesystem access"); return 0;
    }
    if ((argc > 1) && strcmp(argv[1], "golden") == 0)
    {
        unsigned int id = Submit("LOGFILE META 1"); Finish(id);
        id = Submit("LOGFILE READ 1 1-CBF43926-00000009 9"); Finish(id);
        id = Submit("LOGFILE READ 1 1-CBF43926-00000009 0"); Finish(id);
        printf("%s\r\n", s_reply); return 0;
    }
    if ((argc > 1) && strcmp(argv[1], "close-fault") == 0)
    {
        unsigned int id = Submit("LOGFILE META 1"); s_close_error = 1U; Finish(id); assert(strstr(s_reply, "code=IO_ERROR"));
        s_close_error = 0U; id = Submit("LOGFILE META 1"); Finish(id); assert(strstr(s_reply, "code=IO_ERROR"));
        puts("PASS close fault latches service unavailable until reboot"); return 0;
    }
    Normal(); return 0;
}
