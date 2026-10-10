"""Owned generated clock: host algorithm faults plus actual native ARM compilation."""
from pathlib import Path
import shutil
import subprocess
import pytest
from silverstar_fccg.generator.native_clock import NativeClock_FilesRender


@pytest.mark.parametrize('scenario',['normal','wrap','stopped','backwards','gap','port-failure'])
def test_clock_host_boundaries(tmp_path,scenario):
    compiler=shutil.which('gcc')
    if compiler is None:pytest.skip('Host GCC unavailable')
    for p,b in NativeClock_FilesRender(hclk_hz=72_000_000).items():
        dest=tmp_path/p;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(b)
    scg=Path(__file__).resolve().parents[1]
    api=scg/'plugins/builtin/silverstar_platform_api/payload/Platform/Inc'
    (tmp_path/'silverstar_assert.h').write_text('''#include <stdlib.h>
#define SILVERSTAR_ASSERT_MODULE_GENERATED 1U
#define SILVERSTAR_ASSERT_REASON_STATE_INVARIANT 1U
#define SILVERSTAR_ASSERT_REASON_LENGTH_RANGE 2U
#define SILVERSTAR_ASSERT(p,m,r) do { if (!(p)) { abort(); } } while (0)
''',encoding='utf-8')
    harness=tmp_path/'test.c'
    harness.write_text('''#include "native_clock.h"
#include "platform_time.h"
#include <assert.h>
#include <stdint.h>
#include <string.h>
static uint64_t clock_us = 10000ULL;
static uint32_t step = 1U;
static NativeClockResult port_result = NativeClockResult_Ok;
NativeClockResult NativeClockPort_SnapshotGet(NativeClockSnapshot *sample)
{
    if (port_result != NativeClockResult_Ok) { return port_result; }
    clock_us += step;
    sample->tick_ms = (uint32_t)(clock_us / 1000ULL);
    sample->elapsed_cycles = (uint32_t)(clock_us % 1000ULL) * 72U;
    return NativeClockResult_Ok;
}
int main(int argc, char **argv)
{
    uint64_t value = 0xDEADBEEFULL;
    assert(argc == 2);
    assert(NativeClock_Read(&value) == NativeClockResult_NotInitialized);
    assert(value == 0xDEADBEEFULL);
    assert(NativeClock_Read(NULL) == NativeClockResult_InvalidArgument);
    if (strcmp(argv[1],"wrap") == 0) { clock_us = (uint64_t)UINT32_MAX * 1000ULL + 997ULL; }
    assert(PlatformTime_Init() == PLATFORM_OK);
    assert(NativeClock_Read(&value) == NativeClockResult_Ok);
    if (strcmp(argv[1],"normal") == 0 || strcmp(argv[1],"wrap") == 0)
    {
        uint64_t before=value;
        assert(NativeClock_DelayUs(50U) == NativeClockResult_Ok);
        assert(NativeClock_Read(&value) == NativeClockResult_Ok && value-before>=50ULL);
        before=value; PlatformTime_DelayMs(20U);
        assert(NativeClock_Read(&value) == NativeClockResult_Ok && value-before>=20000ULL);
        assert(NativeClock_StatusGet() == NativeClockResult_Ok);
        if (strcmp(argv[1],"wrap") == 0) { assert(value>(uint64_t)UINT32_MAX*1000ULL); }
        assert(PlatformTime_Init() == PLATFORM_ALREADY_INITIALIZED);
        return 0;
    }
    if (strcmp(argv[1],"stopped") == 0)
    { step=0U; assert(NativeClock_DelayUs(2U) == NativeClockResult_Stopped); }
    else if (strcmp(argv[1],"backwards") == 0)
    { clock_us-=5ULL; assert(NativeClock_Read(&value) == NativeClockResult_Discontinuous); }
    else if (strcmp(argv[1],"gap") == 0)
    { clock_us+=10001000ULL; assert(NativeClock_Read(&value) == NativeClockResult_Discontinuous); }
    else
    { port_result=NativeClockResult_InvalidContext; assert(NativeClock_Read(&value)==port_result); }
    value=0xDEADBEEFULL;
    assert(NativeClock_Read(&value) != NativeClockResult_Ok && value==0xDEADBEEFULL);
    assert(PlatformTime_Init() == PLATFORM_NOT_READY);
    return 0;
}
''',encoding='utf-8')
    executable=tmp_path/'test.exe'
    command=[compiler,'-std=c11','-O2','-Wall','-Wextra','-Werror','-Wpedantic','-fanalyzer',
             '-I'+str(tmp_path),'-I'+str(api),'-I'+str(tmp_path/'Generated/Inc'),
             str(tmp_path/'Generated/Src/native_clock.c'),str(harness),'-o',str(executable)]
    result=subprocess.run(command,capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stdout+result.stderr
    run=subprocess.run([str(executable),scenario],capture_output=True,text=True,timeout=30)
    assert run.returncode==0,run.stdout+run.stderr


@pytest.mark.parametrize('hclk',[0,999999,72000001,201000000,True])
def test_clock_unreviewed_frequency_rejected(hclk):
    with pytest.raises(ValueError,match='reviewed HCLK'):NativeClock_FilesRender(hclk_hz=hclk)


def test_clock_port_and_critical_contexts(tmp_path):
    compiler=shutil.which('gcc')
    if compiler is None:pytest.skip('Host GCC unavailable')
    for p,b in NativeClock_FilesRender(hclk_hz=72_000_000).items():
        dest=tmp_path/p;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(b)
    api=Path(__file__).resolve().parents[1]/'plugins/builtin/silverstar_platform_api/payload/Platform/Inc'
    (tmp_path/'silverstar_assert.h').write_text('''#include <stdlib.h>
#define SILVERSTAR_ASSERT_MODULE_GENERATED 1U
#define SILVERSTAR_ASSERT_REASON_STATE_INVARIANT 1U
#define SILVERSTAR_ASSERT(p,m,r) do { if (!(p)) { abort(); } } while (0)
''',encoding='utf-8')
    (tmp_path/'main.h').write_text('''#include <stdint.h>
typedef struct { uint32_t CTRL, LOAD, VAL; } SysTickType;
typedef struct { uint32_t ICSR; } ScbType;
extern SysTickType tick_regs;
extern ScbType scb_regs;
extern uint32_t SystemCoreClock, mask, exception, hclk, hal_tick, changed, tick_frequency;
#define HAL_TICK_FREQ_1KHZ 1U
#define SysTick (&tick_regs)
#define SCB (&scb_regs)
#define SysTick_CTRL_ENABLE_Msk 1U
#define SysTick_CTRL_TICKINT_Msk 2U
#define SysTick_CTRL_CLKSOURCE_Msk 4U
#define SCB_ICSR_PENDSTSET_Msk 0x04000000U
static inline uint32_t __get_PRIMASK(void) { return mask; }
static inline uint32_t __get_IPSR(void) { return exception; }
static inline void __disable_irq(void) { mask=1U; }
static inline void __set_PRIMASK(uint32_t saved) { mask=saved; }
static inline void __DMB(void) { }
static inline uint32_t HAL_RCC_GetHCLKFreq(void) { return hclk; }
static inline uint32_t HAL_GetTickFreq(void) { return tick_frequency; }
uint32_t HAL_GetTick(void);
''',encoding='utf-8')
    harness=tmp_path/'test_port.c'
    harness.write_text('''#include "native_clock.h"
#include "platform_critical.h"
#include "main.h"
#include <assert.h>
SysTickType tick_regs={7U,71999U,71000U};
ScbType scb_regs;
uint32_t SystemCoreClock=72000000U, hclk=72000000U, mask, exception, hal_tick=10U, changed, tick_frequency=1U;
uint32_t HAL_GetTick(void)
{
    if (changed != 0U) { scb_regs.ICSR ^= SCB_ICSR_PENDSTSET_Msk; }
    return hal_tick;
}
int main(void)
{
    NativeClockSnapshot sample={99U,99U};
    assert(NativeClockPort_SnapshotGet(&sample)==NativeClockResult_Ok);
    assert(sample.tick_ms==10U && sample.elapsed_cycles==999U && mask==0U);
    scb_regs.ICSR=SCB_ICSR_PENDSTSET_Msk;
    assert(NativeClockPort_SnapshotGet(&sample)==NativeClockResult_Ok && sample.tick_ms==11U);
    hal_tick=UINT32_MAX;
    assert(NativeClockPort_SnapshotGet(&sample)==NativeClockResult_Ok && sample.tick_ms==0U);
    sample.tick_ms=99U; mask=1U;
    assert(NativeClockPort_SnapshotGet(&sample)==NativeClockResult_InvalidContext && mask==1U && sample.tick_ms==99U);
    PlatformCriticalState saved=PlatformCritical_Enter();
    assert(saved==1U && mask==1U); PlatformCritical_Exit(saved); assert(mask==1U);
    mask=0U; saved=PlatformCritical_Enter(); assert(saved==0U && mask==1U);
    PlatformCritical_Exit(saved); assert(mask==0U);
    exception=15U;
    assert(NativeClockPort_SnapshotGet(&sample)==NativeClockResult_InvalidContext && mask==0U);
    exception=0U; hclk=36000000U;
    assert(NativeClockPort_SnapshotGet(&sample)==NativeClockResult_InvalidConfiguration);
    hclk=72000000U; tick_frequency=10U; sample.tick_ms=99U;
    assert(NativeClockPort_SnapshotGet(&sample)==NativeClockResult_InvalidConfiguration && sample.tick_ms==99U);
    tick_frequency=1U; tick_regs.VAL=0U;
    assert(NativeClockPort_SnapshotGet(&sample)==NativeClockResult_UnstableSnapshot && mask==0U);
    tick_regs.VAL=71000U; changed=1U;
    assert(NativeClockPort_SnapshotGet(&sample)==NativeClockResult_UnstableSnapshot && mask==0U);
    return 0;
}
''',encoding='utf-8')
    executable=tmp_path/'test_port.exe'
    command=[compiler,'-std=c11','-Wall','-Wextra','-Werror','-Wpedantic','-fanalyzer',
        '-I'+str(tmp_path),'-I'+str(api),'-I'+str(tmp_path/'Generated/Inc'),
        str(tmp_path/'Generated/Src/native_clock_port.c'),str(tmp_path/'Generated/Src/native_critical.c'),
        str(harness),'-o',str(executable)]
    result=subprocess.run(command,capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stdout+result.stderr
    run=subprocess.run([str(executable)],capture_output=True,text=True,timeout=30)
    assert run.returncode==0,run.stdout+run.stderr
