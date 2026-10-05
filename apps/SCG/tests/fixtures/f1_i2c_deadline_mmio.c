/* Actual F1 HAL memory transaction and deadline helper with a deterministic
 * Host-only peripheral/CYCCNT/IRQ model. This is not wire or MCU timing. */
#include "f1_i2c_mmio_model.h"
#include "silverstar_assert.h"
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

enum { NONE, BUSY, START1, ADDR1, MEM_HIGH, MEM_LOW, MEM_END,
       START2, ADDR2, DATA_TXE, DATA_BTF, DATA_RXNE, DATA_BTF_MASKED };
static I2C_TypeDef s_registers;
static I2C_HandleTypeDef s_handle;
static DWT_Type s_dwt;
static CoreDebug_Type s_debug;
static uint32_t s_time_us, s_seed_cycles, s_irq, s_exception;
static uint32_t s_phase, s_phase_since, s_fault_phase, s_error_flag;
static uint32_t s_busy_delay_us, s_data_delay_us, s_start_count, s_clear_count;
static uint32_t s_frozen, s_masked_polls;
static uint32_t s_context_corrupt_mode;
static uint16_t s_mem_size;
static int s_read;

static void Check(int condition, unsigned line)
{ if (!condition) { fprintf(stderr,"FAIL line=%u phase=%lu time_us=%lu err=%lu\n",
    line,(unsigned long)s_phase,(unsigned long)s_time_us,
    (unsigned long)s_handle.ErrorCode); exit(1); } }
#define CHECK(condition_) Check((condition_) != 0, __LINE__)

void SilverStarAssert_Check(uint8_t condition,SilverStarAssertModuleId module,
    const char *file,uint32_t line,SilverStarAssertReasonId reason)
{
    (void)module;(void)file;(void)line;(void)reason;
    if (condition == 0U) { fputs("ASSERT_TRAP: invalid stored deadline lifecycle\n",stderr);exit(1); }
}

static void Advance(void)
{
    s_time_us += 2U;
    if ((s_frozen == 0U) && ((s_dwt.CTRL & DWT_CTRL_CYCCNTENA_Msk) != 0U))
    { s_dwt.CYCCNT = s_seed_cycles + s_time_us * 64U; }
    if ((s_error_flag != 0U) && (s_phase == s_fault_phase))
    { s_registers.SR1 |= s_error_flag; }
    if (s_phase == ADDR1)
    {
        if (s_context_corrupt_mode == 1U) { s_handle.MemoryDeadline.active=0U; }
        if (s_context_corrupt_mode == 2U) { s_handle.BlockingMemoryOwner=0U; }
        if (s_context_corrupt_mode == 3U) { s_handle.Lock=HAL_UNLOCKED; }
    }
}
DWT_Type *HostDwt_Get(void) { Advance(); return &s_dwt; }
CoreDebug_Type *HostCoreDebug_Get(void) { return &s_debug; }
void HostIrq_Disable(void) { CHECK(s_irq == 0U); s_irq = 1U; }
void HostIrq_Enable(void) { CHECK(s_irq == 1U); s_irq = 0U; }
uint32_t HostIrq_MaskGet(void) { return s_irq; }
uint32_t HostIrq_ExceptionGet(void) { return s_exception; }
uint32_t HAL_GetTick(void) { Advance(); return s_time_us / 1000U; }
uint32_t HAL_RCC_GetHCLKFreq(void) { return 64000000U; }
uint32_t HAL_RCC_GetPCLK1Freq(void) { return 32000000U; }
uint32_t SystemCoreClock = 64000000U;

HAL_StatusTypeDef HAL_DMA_Start_IT(DMA_HandleTypeDef *h,uint32_t a,uint32_t b,uint32_t c)
{ (void)h;(void)a;(void)b;(void)c;CHECK(0);return HAL_ERROR; }
HAL_StatusTypeDef HAL_DMA_Abort_IT(DMA_HandleTypeDef *h)
{ (void)h;CHECK(0);return HAL_ERROR; }
HAL_StatusTypeDef HAL_DMA_Abort(DMA_HandleTypeDef *h)
{ (void)h;CHECK(0);return HAL_ERROR; }
HAL_DMA_StateTypeDef HAL_DMA_GetState(DMA_HandleTypeDef *h)
{ (void)h;CHECK(0);return HAL_DMA_STATE_RESET; }

static void PhaseSet(uint32_t phase)
{
    if (s_phase != phase) { s_phase=phase;s_phase_since=s_time_us; }
}
uint32_t HostI2c_FlagGet(I2C_HandleTypeDef *h,uint32_t flag)
{
    uint32_t phase;
    CHECK(h == &s_handle);
    if (flag == I2C_FLAG_AF) { return (s_registers.SR1 & I2C_SR1_AF) ? SET : RESET; }
    if (flag == I2C_FLAG_STOPF) { return RESET; }
    if (flag == I2C_FLAG_BUSY)
    {
        PhaseSet(BUSY);
        return ((s_fault_phase == BUSY) || (s_time_us < s_busy_delay_us)) ? SET : RESET;
    }
    if (flag == I2C_FLAG_SB)
    {
        if ((s_phase != START1) && (s_phase != START2))
        { s_start_count++;PhaseSet(s_start_count == 1U ? START1 : START2); }
        phase=s_phase;
    }
    else if (flag == I2C_FLAG_ADDR)
    { phase=s_start_count == 1U ? ADDR1 : ADDR2;PhaseSet(phase); }
    else if (flag == I2C_FLAG_TXE)
    {
        if (h->Instance->DR == 0x12U) { phase=MEM_LOW; }
        else if (h->Instance->DR == 0x34U) { phase=s_read ? MEM_END : DATA_TXE; }
        else if ((s_phase == DATA_TXE) || (s_phase == DATA_BTF)) { phase=DATA_TXE; }
        else { phase=MEM_HIGH; }
        PhaseSet(phase);
    }
    else if (flag == I2C_FLAG_BTF)
    {
        /* F1 memory-read request waits for TXE before repeated START, not BTF.
         * These BTF accesses belong to data/final-write receive sequencing. */
        CHECK(!s_read || s_start_count == 2U);
        phase=DATA_BTF;
        if (s_read && s_irq != 0U) { phase=DATA_BTF_MASKED;s_masked_polls++; }
        PhaseSet(phase);
    }
    else if (flag == I2C_FLAG_RXNE) { phase=DATA_RXNE;PhaseSet(phase); }
    else { CHECK(0);return RESET; }
    if ((s_error_flag != 0U) && (phase == s_fault_phase))
    { s_registers.SR1 |= s_error_flag;return RESET; }
    if (phase == s_fault_phase) { return RESET; }
    if ((s_data_delay_us != 0U) && ((phase == DATA_RXNE) || (phase == DATA_TXE)) &&
        (s_time_us - s_phase_since < s_data_delay_us))
    { return RESET; }
    if ((phase == START1) || (phase == START2))
    { s_registers.CR1 &= ~I2C_CR1_START;s_registers.SR2 |= I2C_SR2_MSL | I2C_SR2_BUSY; }
    if (s_read && s_start_count == 2U && ((flag == I2C_FLAG_RXNE) || (flag == I2C_FLAG_BTF)))
    { s_registers.DR=0xAAU; }
    return SET;
}
void HostI2c_AddressClear(I2C_HandleTypeDef *h)
{ CHECK(h == &s_handle);s_clear_count++;h->Instance->SR1 &= ~I2C_SR1_ADDR; }

static void Reset(int read)
{
    memset(&s_handle,0,sizeof(s_handle));memset(&s_registers,0,sizeof(s_registers));
    memset(&s_dwt,0,sizeof(s_dwt));memset(&s_debug,0,sizeof(s_debug));
    s_handle.Instance=&s_registers;s_handle.State=HAL_I2C_STATE_READY;
    s_registers.CR1=I2C_CR1_PE | I2C_CR1_ACK;
    s_time_us=0U;s_seed_cycles=0U;s_irq=0U;s_exception=0U;s_phase=NONE;
    s_phase_since=0U;s_fault_phase=NONE;s_error_flag=0U;s_busy_delay_us=0U;
    s_data_delay_us=0U;s_start_count=0U;s_clear_count=0U;s_frozen=0U;
    s_masked_polls=0U;s_context_corrupt_mode=0U;s_read=read;s_mem_size=I2C_MEMADD_SIZE_16BIT;
}
static HAL_StatusTypeDef Run(uint16_t size)
{
    uint8_t guarded[66];HAL_StatusTypeDef result;
    CHECK(size <= 64U);memset(guarded,0x55,sizeof(guarded));
    if (s_read) { result=HAL_I2C_Mem_Read(&s_handle,0xD0U,0x1234U,
        s_mem_size,&guarded[1],size,2U); }
    else { result=HAL_I2C_Mem_Write(&s_handle,0xD0U,0x1234U,
        s_mem_size,&guarded[1],size,2U); }
    printf("I2C_CASE read=%d size=%u fault_phase=%lu error_flag=%lu result=%u model_us=%lu irq=%lu\n",
        s_read,size,(unsigned long)s_fault_phase,(unsigned long)s_error_flag,
        result,(unsigned long)s_time_us,(unsigned long)s_irq);fflush(stdout);
    CHECK(guarded[0] == 0x55U && guarded[size+1U] == 0x55U);
    if (result == HAL_OK && s_read)
    { for (unsigned i=1U;i<=size;i++) { CHECK(guarded[i] == 0xAAU); } }
    CHECK(s_irq == 0U && s_handle.Lock == HAL_UNLOCKED);
    CHECK(s_handle.State == HAL_I2C_STATE_READY && s_handle.Mode == HAL_I2C_MODE_NONE);
    CHECK(s_handle.MemoryDeadline.active == 0U);
    CHECK(s_handle.BlockingMemoryOwner == 0U);
    CHECK((s_registers.CR1 & (I2C_CR1_ACK | I2C_CR1_POS)) == I2C_CR1_ACK);
    return result;
}
int main(int argc,char **argv)
{
    if (argc == 2)
    {
        Reset(1);
        if (strcmp(argv[1],"--lost-active") == 0) { s_context_corrupt_mode=1U; }
        if (strcmp(argv[1],"--lost-owner") == 0) { s_context_corrupt_mode=2U; }
        if (strcmp(argv[1],"--lost-lock") == 0) { s_context_corrupt_mode=3U; }
        if (s_context_corrupt_mode != 0U) { (void)Run(1U);CHECK(0); }
        if (strcmp(argv[1],"--corrupt-active") == 0)
        { s_handle.MemoryDeadline.active=2U;s_handle.MemoryDeadline.budget_cycles=1U; }
        else if (strcmp(argv[1],"--corrupt-budget") == 0)
        { s_handle.MemoryDeadline.active=1U;s_handle.MemoryDeadline.budget_cycles=0U; }
        else if (strcmp(argv[1],"--double-start") == 0)
        {
            s_handle.MemoryDeadline.active=1U;
            (void)PlatformI2cDeadline_Start(&s_handle.MemoryDeadline,2U);
            CHECK(0);
        }
        else { CHECK(0); }
        (void)PlatformI2cDeadline_Expired(&s_handle.MemoryDeadline);CHECK(0);
    }
    const uint32_t read_faults[]={BUSY,START1,ADDR1,MEM_HIGH,MEM_LOW,MEM_END,
        START2,ADDR2,DATA_RXNE,DATA_BTF,DATA_BTF_MASKED};
    const uint32_t write_faults[]={BUSY,START1,ADDR1,MEM_HIGH,MEM_LOW,DATA_TXE,DATA_BTF};
    const uint16_t sizes[]={1U,2U,3U,4U,6U,14U,24U};
    const uint32_t errors[]={I2C_SR1_AF,I2C_SR1_BERR,I2C_SR1_ARLO,I2C_SR1_OVR};
    Reset(1);s_handle.State=HAL_I2C_STATE_RESET;
    s_handle.Init.ClockSpeed=350000U;s_handle.Init.DutyCycle=I2C_DUTYCYCLE_2;
    s_handle.Init.AddressingMode=I2C_ADDRESSINGMODE_7BIT;
    s_handle.Init.DualAddressMode=I2C_DUALADDRESS_DISABLE;
    s_handle.Init.GeneralCallMode=I2C_GENERALCALL_DISABLE;
    s_handle.Init.NoStretchMode=I2C_NOSTRETCH_DISABLE;
    CHECK(HAL_I2C_Init(&s_handle) == HAL_OK);
    CHECK((s_registers.CCR & I2C_CCR_CCR) == 31U);
    CHECK((s_registers.CCR & I2C_CCR_FS) != 0U);
    CHECK(s_registers.TRISE == 10U);
    puts("I2C_INIT_REG PCLK1=32000000 CCR=31 duty=2 nominal_SCL=344086 guarded_upper_SCL=378495");
    for (unsigned i=0;i<sizeof(read_faults)/sizeof(read_faults[0]);i++)
    {
        Reset(1);s_fault_phase=read_faults[i];
        uint16_t size=(s_fault_phase == DATA_BTF_MASKED) ? 3U :
            ((s_fault_phase == DATA_BTF) ? 2U : 1U);
        CHECK(Run(size) == HAL_TIMEOUT);CHECK(s_time_us <= 2000U);
        if (s_fault_phase == DATA_BTF_MASKED) { CHECK(s_masked_polls != 0U); }
    }
    for (unsigned i=0;i<sizeof(write_faults)/sizeof(write_faults[0]);i++)
    { Reset(0);s_fault_phase=write_faults[i];CHECK(Run(1U) == HAL_TIMEOUT);CHECK(s_time_us <= 2000U); }
    for (unsigned i=0;i<sizeof(sizes)/sizeof(sizes[0]);i++)
    { Reset(1);CHECK(Run(sizes[i]) == HAL_OK);CHECK(s_start_count == 2U && s_clear_count == 2U); }
    Reset(0);CHECK(Run(6U) == HAL_OK);CHECK(s_start_count == 1U);
    Reset(1);s_mem_size=I2C_MEMADD_SIZE_8BIT;CHECK(Run(14U) == HAL_OK);
    Reset(1);s_mem_size=I2C_MEMADD_SIZE_8BIT;CHECK(Run(24U) == HAL_OK);
    Reset(0);s_mem_size=I2C_MEMADD_SIZE_8BIT;CHECK(Run(6U) == HAL_OK);
    for (unsigned i=0;i<sizeof(errors)/sizeof(errors[0]);i++)
    {
        Reset(1);s_fault_phase=ADDR1;s_error_flag=errors[i];CHECK(Run(1U) == HAL_ERROR);
        CHECK((s_handle.ErrorCode & HAL_I2C_ERROR_TIMEOUT) == 0U);
        if (errors[i] == I2C_SR1_ARLO) { CHECK((s_registers.CR1 & I2C_CR1_STOP) == 0U); }
    }
    const uint32_t nack_read_phases[]={MEM_HIGH,MEM_LOW,START2,ADDR2,DATA_RXNE,DATA_BTF_MASKED};
    for (unsigned i=0;i<sizeof(nack_read_phases)/sizeof(nack_read_phases[0]);i++)
    {
        Reset(1);s_fault_phase=nack_read_phases[i];s_error_flag=I2C_SR1_AF;
        CHECK(Run(s_fault_phase == DATA_BTF_MASKED ? 3U : 1U) == HAL_ERROR);
        CHECK((s_handle.ErrorCode & HAL_I2C_ERROR_AF) != 0U);
        CHECK((s_handle.ErrorCode & HAL_I2C_ERROR_TIMEOUT) == 0U);
    }
    Reset(0);s_fault_phase=DATA_TXE;s_error_flag=I2C_SR1_AF;
    CHECK(Run(1U) == HAL_ERROR);CHECK(s_handle.ErrorCode == HAL_I2C_ERROR_AF);
    Reset(1);s_busy_delay_us=1000U;s_data_delay_us=900U;
    CHECK(Run(1U) == HAL_TIMEOUT);CHECK(s_time_us <= 2000U);
    Reset(0);s_busy_delay_us=800U;s_data_delay_us=1100U;
    CHECK(Run(1U) == HAL_TIMEOUT);CHECK(s_time_us <= 2000U);
    Reset(1);s_seed_cycles=UINT32_MAX-6400U;s_dwt.CYCCNT=s_seed_cycles;
    CHECK(Run(14U) == HAL_OK);
    Reset(1);s_seed_cycles=UINT32_MAX-6400U;s_dwt.CYCCNT=s_seed_cycles;s_fault_phase=BUSY;
    CHECK(Run(1U) == HAL_TIMEOUT);CHECK(s_time_us <= 2000U);
    Reset(1);s_frozen=1U;CHECK(Run(1U) == HAL_TIMEOUT);CHECK(s_start_count == 0U);
    Reset(1);s_fault_phase=DATA_RXNE;CHECK(Run(1U) == HAL_TIMEOUT);
    s_fault_phase=NONE;s_registers.SR2=0U;s_registers.DR=0U;s_phase=NONE;
    s_start_count=0U;s_clear_count=0U;CHECK(Run(1U) == HAL_OK);
    uint8_t byte=0U;
    Reset(1);s_irq=1U;
    CHECK(HAL_I2C_Mem_Read(&s_handle,0xD0U,0x34U,I2C_MEMADD_SIZE_8BIT,&byte,1U,2U) == HAL_ERROR);
    CHECK(s_irq == 1U && s_start_count == 0U && s_handle.Lock == HAL_UNLOCKED);
    Reset(1);s_exception=16U;
    CHECK(HAL_I2C_Mem_Read(&s_handle,0xD0U,0x34U,I2C_MEMADD_SIZE_8BIT,&byte,1U,2U) == HAL_ERROR);
    CHECK(s_start_count == 0U && s_handle.Lock == HAL_UNLOCKED);
    Reset(1);
    CHECK(HAL_I2C_Mem_Read(NULL,0xD0U,0x34U,I2C_MEMADD_SIZE_8BIT,&byte,1U,2U) == HAL_ERROR);
    CHECK(HAL_I2C_Mem_Read(&s_handle,0xD0U,0x34U,I2C_MEMADD_SIZE_8BIT,NULL,1U,2U) == HAL_ERROR);
    CHECK(HAL_I2C_Mem_Read(&s_handle,0xD0U,0x34U,I2C_MEMADD_SIZE_8BIT,&byte,0U,2U) == HAL_ERROR);
    CHECK(HAL_I2C_Mem_Read(&s_handle,0xD1U,0x34U,I2C_MEMADD_SIZE_8BIT,&byte,1U,2U) == HAL_ERROR);
    CHECK(HAL_I2C_Mem_Read(&s_handle,0xD0U,0x34U,0U,&byte,1U,2U) == HAL_ERROR);
    CHECK(HAL_I2C_Mem_Read(&s_handle,0xD0U,0x34U,I2C_MEMADD_SIZE_8BIT,&byte,1U,0U) == HAL_ERROR);
    CHECK(HAL_I2C_Mem_Read(&s_handle,0xD0U,0x34U,I2C_MEMADD_SIZE_8BIT,&byte,1U,1001U) == HAL_ERROR);
    CHECK(s_start_count == 0U && s_handle.MemoryDeadline.active == 0U);
    s_handle.State=HAL_I2C_STATE_BUSY_TX;
    CHECK(HAL_I2C_Mem_Read(&s_handle,0xD0U,0x34U,I2C_MEMADD_SIZE_8BIT,&byte,1U,2U) == HAL_BUSY);
    Reset(1);s_handle.Lock=HAL_LOCKED;
    CHECK(HAL_I2C_Mem_Read(&s_handle,0xD0U,0x34U,I2C_MEMADD_SIZE_8BIT,&byte,1U,2U) == HAL_BUSY);
    CHECK(s_handle.Lock == HAL_LOCKED && s_start_count == 0U);
    puts("I2C_DEADLINE_MMIO PASS; deterministic Host time only; MCU/wire timing NOT RUN");
    return 0;
}
