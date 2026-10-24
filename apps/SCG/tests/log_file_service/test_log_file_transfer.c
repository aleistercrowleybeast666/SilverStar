/* Deterministic real service/adapter regressions; no target or TF access. */
#define main ExistingFixture_Main
#include "test_log_file_service.c"
#undef main

static char s_token[32];

static void Metadata(uint32_t size)
{
    unsigned int id;
    const char *token;
    s_pattern_enabled = 1U; s_pattern_size = size;
    id = Submit("LOGFILE META 1"); Finish(id);
    assert(strstr(s_reply, "OK LOGFILE META") != NULL);
    token = strstr(s_reply, "token="); assert(token != NULL);
    assert(sscanf(token, "token=%31s", s_token) == 1);
    assert(s_live_handles == 0U);
}

static unsigned int Read(uint32_t offset)
{
    char command[128];
    assert(snprintf(command, sizeof(command), "LOGFILE READ 1 %s %lu",
        s_token, (unsigned long)offset) > 0);
    return Submit(command);
}

static void Cancel(void)
{
    Execute("LOGFILE CANCEL"); assert(strstr(s_reply,"cleanup_complete=0"));
    SystemLogFile_Process(1U); assert(s_live_handles == 0U);
}

static void Sequential(void)
{
    unsigned int id;
    uint32_t opened;
    uint32_t seeks;
    uint32_t before;
    Metadata(512U); opened=s_open_count; seeks=s_seek_count;
    id=Read(0U); Finish(id); assert(strstr(s_reply,"length=64"));
    id=Read(64U); Finish(id); assert(strstr(s_reply,"offset=64"));
    assert(s_open_count-opened==1U); assert(s_live_handles==1U);
    assert(s_seek_count==seeks);
    before=s_io_count; Poll(id); Poll(id); assert(s_io_count==before);
    id=Read(64U); Finish(id); assert(strstr(s_reply,"offset=64"));
    assert(s_open_count-opened==1U && s_seek_count-seeks==1U);
    Cancel(); assert(s_close_count==s_open_count);
}

static void Budget(void)
{
    unsigned int id;
    s_pattern_enabled=1U; s_pattern_size=8192U; s_query_in_read=1U;
    id=Submit("LOGFILE META 1"); SystemLogFile_Process(1U);
    assert(s_read_count>=2U && s_read_count<=8U);
    assert(s_serial_queries==s_read_count);
    Poll(id); assert(strncmp(s_reply,"PENDING ",8U)==0);
    Execute("LOGFILE META 1"); assert(strstr(s_reply,"code=BUSY"));
    Finish(id); assert(strstr(s_reply,"OK LOGFILE META"));
    Cancel();
}

static void TimedBudget(void)
{
    uint64_t start;
    s_pattern_enabled=1U; s_pattern_size=8192U; s_io_cost_us=700U;
    (void)Submit("LOGFILE META 1"); start=s_now;
    SystemLogFile_Process(1U);
    assert(s_now-start<=2700U);
    assert(s_read_count>0U && s_read_count<8U);
    Cancel();
}

static void Failure(const char *kind)
{
    unsigned int id;
    Metadata(512U); id=Read(0U); Finish(id);
    assert(s_live_handles==1U);
    if (strcmp(kind,"short-read")==0) { s_short_read=1U; }
    else if (strcmp(kind,"read-error")==0) { s_read_error=1U; }
    else if (strcmp(kind,"seek-error")==0) { s_seek_error=1U; }
    else if (strcmp(kind,"lifecycle")==0) { s_lifecycle=SYSTEM_STATE_FLIGHT; }
    else if (strcmp(kind,"size-change")==0) { s_size_change=1U; }
    else { assert(0); }
    id=Read(0U); Finish(id);
    assert(strncmp(s_reply,"ERR LOGFILE READ ",17U)==0);
    assert(s_live_handles==0U);
}

static void IdleAndReconnect(void)
{
    unsigned int id;
    Metadata(512U); id=Read(0U); Finish(id); assert(s_live_handles==1U);
    s_now+=30000001ULL; SystemLogFile_Process(1U); Poll(id);
    assert(strstr(s_reply,"code=TIMEOUT") && s_live_handles==0U);
    id=Read(64U); Finish(id); assert(strstr(s_reply,"code=STALE"));
    Metadata(512U); id=Read(0U); Finish(id); assert(strstr(s_reply,"OK LOGFILE READ"));
    Cancel();
}

static void CancelQuantum(void)
{
    unsigned int id;
    s_pattern_enabled=1U; s_pattern_size=8192U; s_cancel_in_read=1U;
    id=Submit("LOGFILE META 1"); SystemLogFile_Process(1U); Poll(id);
    assert(strstr(s_reply,"code=CANCELLED"));
    assert(s_read_count==1U && s_live_handles==0U);
}

static void Boundary(uint32_t size)
{
    unsigned int id;
    uint32_t offset=0U;
    Metadata(size);
    do
    {
        uint32_t count=(size-offset>64U)?64U:size-offset;
        char expected[40];
        id=Read(offset); Finish(id);
        assert(snprintf(expected,sizeof(expected),"length=%lu ",(unsigned long)count)>0);
        assert(strstr(s_reply,"OK LOGFILE READ") && strstr(s_reply,expected));
        offset+=count;
    } while (offset<size);
    Cancel();
}

static void CloseFailure(void)
{
    uint32_t size=0U;
    s_pattern_enabled=1U; s_pattern_size=512U;
    assert(SystemLogFileStorage_HashBegin(1U,&size)==SystemLogFileResult_Ok);
    s_close_error=1U;
    assert(SystemLogFileStorage_Reset()==SystemLogFileResult_IoError);
    assert(s_live_handles==1U);
    s_close_error=0U;
    assert(SystemLogFileStorage_Reset()==SystemLogFileResult_IoError);
    assert(s_live_handles==0U);
    assert(SystemLogFileStorage_Check(1U,0U)==SystemLogFileResult_IoError);
}

int main(int argc,char **argv)
{
    assert(argc==2);
    if (strcmp(argv[1],"sequential")==0) { Sequential(); }
    else if (strcmp(argv[1],"budget")==0) { Budget(); }
    else if (strcmp(argv[1],"timed-budget")==0) { TimedBudget(); }
    else if (strcmp(argv[1],"idle-reconnect")==0) { IdleAndReconnect(); }
    else if (strcmp(argv[1],"cancel-quantum")==0) { CancelQuantum(); }
    else if (strcmp(argv[1],"close-failure")==0) { CloseFailure(); }
    else if (strncmp(argv[1],"size=",5U)==0) { Boundary((uint32_t)strtoul(argv[1]+5,NULL,10)); }
    else { Failure(argv[1]); }
    assert(s_live_handles==0U);
    puts("PASS bounded service/reader regression");
    return 0;
}
