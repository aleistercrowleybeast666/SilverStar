#include <stdint.h>
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
