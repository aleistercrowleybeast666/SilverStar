#ifndef __F1_I2C_MMIO_MODEL_H
#define __F1_I2C_MMIO_MODEL_H

/* Host-only CPU/peripheral model. The tested HAL transaction/sequencing and
 * deadline algorithm remain their actual owning sources. No target define. */
#include "stm32f1xx_hal.h"
DWT_Type *HostDwt_Get(void);
CoreDebug_Type *HostCoreDebug_Get(void);
uint32_t HostI2c_FlagGet(I2C_HandleTypeDef *handle, uint32_t flag);
void HostI2c_AddressClear(I2C_HandleTypeDef *handle);
void HostIrq_Disable(void);
void HostIrq_Enable(void);
uint32_t HostIrq_MaskGet(void);
uint32_t HostIrq_ExceptionGet(void);

#undef DWT
#undef CoreDebug
#define DWT HostDwt_Get()
#define CoreDebug HostCoreDebug_Get()
#define __disable_irq HostIrq_Disable
#define __enable_irq HostIrq_Enable
#define __get_PRIMASK HostIrq_MaskGet
#define __get_IPSR HostIrq_ExceptionGet
#define __DSB() ((void)0)
#define __NOP() ((void)0)
#undef __HAL_I2C_GET_FLAG
#undef __HAL_I2C_CLEAR_ADDRFLAG
#define __HAL_I2C_GET_FLAG(handle_, flag_) HostI2c_FlagGet(handle_, flag_)
#define __HAL_I2C_CLEAR_ADDRFLAG(handle_) HostI2c_AddressClear(handle_)

#endif /* __F1_I2C_MMIO_MODEL_H */
