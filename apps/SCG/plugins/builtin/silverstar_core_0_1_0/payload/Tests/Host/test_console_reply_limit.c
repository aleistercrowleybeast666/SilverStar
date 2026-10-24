/* Reuse the real Console endpoint fixture with a deliberately small response
 * capacity. The normal console suite still executes independently in full. */
#define main OriginalConsoleFixture_Main
#include "test_console.c"
#undef main

int main(void)
{
    const char command[]="SYSTEM INFO\r\n";
    TEST_CHECK(SystemConsole_Init()==SYSTEM_DEVICE_OK);
    memset(s_console_write_buffer,0,sizeof(s_console_write_buffer));
    memcpy(s_console_read_buffer,command,sizeof(command)-1U);
    s_console_read_length=(uint16_t)(sizeof(command)-1U);
    s_console_read_pending=1U;
    SystemConsole_Process();
    size_t length=strlen(s_console_write_buffer);
    TEST_CHECK(strncmp(s_console_write_buffer,"OK SYSTEM INFO ",15U)==0);
    TEST_CHECK(length>=2U && length<=SYSTEM_CONSOLE_RESPONSE_CAPACITY-1U);
    TEST_CHECK(length>=2U && s_console_write_buffer[length-2U]=='\r' && s_console_write_buffer[length-1U]=='\n');
    return Test_Finish("console_reply_limit");
}
