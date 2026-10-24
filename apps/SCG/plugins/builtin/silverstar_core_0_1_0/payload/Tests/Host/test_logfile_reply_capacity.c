/* Host-only synthetic completed mailbox: no filesystem, device or run control. */
#include <stdint.h>
#include <string.h>
#include "platform_critical.h"
#include "test_common.h"
static unsigned s_depth;
PlatformCriticalState PlatformCritical_Enter(void) { return s_depth++; }
void PlatformCritical_Exit(PlatformCriticalState previous)
{ TEST_CHECK(s_depth==previous+1U);s_depth=previous; }
uint64_t SystemTime_GetMonotonicUs(void) { return 1000ULL; }
#include "system_log_file.c"

int main(void)
{
    struct { uint8_t before[16];char response[64];uint8_t after[16]; } guarded;
    char full[256];
    memset(&guarded,0xA5,sizeof(guarded));
    memset(&s_mailbox,0,sizeof(s_mailbox));s_mailbox.state=LOG_FILE_DONE;
    s_mailbox.request.id=9U;s_mailbox.request.operation=LOG_FILE_READ;
    memset(s_mailbox.response.text,'R',255U);s_mailbox.response.text[255]='\0';
    LogFile_Poll(9U,guarded.response,sizeof(guarded.response));
    for (unsigned i=0U;i<16U;i++)
    { TEST_CHECK(guarded.before[i]==0xA5U);TEST_CHECK(guarded.after[i]==0xA5U); }
    TEST_CHECK(strstr(guarded.response,"ERR LOGFILE POLL request_id=9 code=BAD_ARGUMENT")!=NULL);
    TEST_CHECK(s_mailbox.state==LOG_FILE_DONE && s_mailbox.request.id==9U && s_depth==0U);
    LogFile_Poll(9U,full,sizeof(full));
    TEST_CHECK(memcmp(full,s_mailbox.response.text,sizeof(full))==0);
    TEST_CHECK(s_mailbox.state==LOG_FILE_DONE && s_depth==0U);
    static const char short_response[]="OK LOGFILE READ request_id=9";
    memcpy(s_mailbox.response.text,short_response,sizeof(short_response));
    LogFile_Poll(9U,guarded.response,sizeof(guarded.response));
    TEST_CHECK(strcmp(guarded.response,"OK LOGFILE READ request_id=9")==0);
    return Test_Finish("logfile_reply_capacity");
}
