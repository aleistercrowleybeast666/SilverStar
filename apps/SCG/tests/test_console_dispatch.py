"""The real dispatch TU preserves validation, owner exclusion and result codes."""
from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.mark.parametrize('enabled',[0,1])
def test_console_dispatch_routes_without_entering_diagnostic_owner(tmp_path,enabled):
    core=Path(__file__).resolve().parents[1]/'plugins/builtin/silverstar_core_0_1_0/payload'
    harness=tmp_path/'dispatch.c'
    harness.write_text(r'''
#include "system_console_dispatch.h"
#include "system_installation_capture_if.h"
#include "system_log_file.h"
#include "system_time.h"
#include <assert.h>
#include <string.h>
static unsigned s_commands, s_install, s_logfile;
static uint8_t s_blocked;
uint64_t SystemTime_GetMonotonicUs(void) {return 123456U;}
#if SYSTEM_INSTALLATION_CAPTURE_ENABLED
uint8_t SystemInstallationCapture_CommandBlocked(void) {return s_blocked;}
void SystemInstallationCapture_ExecuteLine(const char *line,char *response,uint16_t capacity,uint64_t now)
{assert(strncmp(line,"INSTALL ",8)==0);assert(response!=NULL&&capacity!=0);assert(now==123456U);s_install++;}
#endif
SystemConsoleExecuteResult SystemConsole_CommandsExecute(const char *line,char *response,uint16_t capacity)
{assert(line!=NULL&&response!=NULL&&capacity!=0);s_commands++;return SYSTEM_CONSOLE_EXECUTE_BAD_COMMAND;}
SystemConsoleExecuteResult SystemLogFile_ExecuteLine(const char *line,char *response,uint16_t capacity)
{assert(strncmp(line,"LOGFILE ",8)==0);assert(response!=NULL&&capacity!=0);s_logfile++;return SYSTEM_CONSOLE_EXECUTE_LOCKED;}
int main(void)
{
 char response[96]={0};
 assert(SystemConsole_ExecuteLine(NULL,response,sizeof(response))==SYSTEM_CONSOLE_EXECUTE_BAD_ARGUMENT);
 assert(SystemConsole_ExecuteLine("INSTALL ACTIVE",NULL,96)==SYSTEM_CONSOLE_EXECUTE_BAD_ARGUMENT);
 assert(SystemConsole_ExecuteLine("INSTALL ACTIVE",response,0)==SYSTEM_CONSOLE_EXECUTE_BAD_ARGUMENT);
 assert(s_commands==0&&s_install==0&&s_logfile==0);
 assert(SystemConsole_ExecuteLine("SYSTEM INFO",response,sizeof(response))==SYSTEM_CONSOLE_EXECUTE_BAD_COMMAND);
 assert(s_commands==1);
 assert(SystemConsole_ExecuteLine("LOGFILE STATUS",response,sizeof(response))==SYSTEM_CONSOLE_EXECUTE_LOCKED);
 assert(s_logfile==1);
 if(SYSTEM_INSTALLATION_CAPTURE_ENABLED!=0U) {
  assert(SystemConsole_ExecuteLine("INSTALL ACTIVE",response,sizeof(response))==SYSTEM_CONSOLE_EXECUTE_OK);
  assert(s_install==1&&s_commands==1&&s_logfile==1);
  s_blocked=1;
  assert(SystemConsole_ExecuteLine("SYSTEM INFO",response,sizeof(response))==SYSTEM_CONSOLE_EXECUTE_OK);
  assert(strstr(response,"BUSY")!=NULL&&s_commands==1);
  assert(SystemConsole_ExecuteLine("LOGFILE STATUS",response,sizeof(response))==SYSTEM_CONSOLE_EXECUTE_OK);
  assert(s_logfile==1);
  assert(SystemConsole_ExecuteLine("INSTALL CANCEL",response,sizeof(response))==SYSTEM_CONSOLE_EXECUTE_OK);
  assert(s_install==2);
 } else {
  assert(SystemConsole_ExecuteLine("INSTALL ACTIVE",response,sizeof(response))==SYSTEM_CONSOLE_EXECUTE_BAD_COMMAND);
  assert(s_install==0&&s_commands==2);
 }
 return 0;
}
''',encoding='utf8')
    executable=tmp_path/'dispatch.exe'
    command=[shutil.which('gcc'),'-std=c11','-O2','-Wall','-Wextra','-Werror','-pedantic',
        f'-DSYSTEM_INSTALLATION_CAPTURE_ENABLED={enabled}U',
        *['-I'+str(core/path) for path in ('System/Inc','Interfaces/Inc','Common/Inc')],
        str(core/'System/Src/system_console_dispatch.c'),str(core/'Common/Src/common_format.c'),
        str(core/'Common/Src/silverstar_assert.c'),str(harness),'-o',str(executable)]
    compiled=subprocess.run(command,capture_output=True,text=True,timeout=60)
    assert compiled.returncode==0,compiled.stderr
    executed=subprocess.run([str(executable)],capture_output=True,text=True,timeout=15)
    assert executed.returncode==0,executed.stderr
