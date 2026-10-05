#ifndef __STM32F1XX_HAL_CONF_H
#define __STM32F1XX_HAL_CONF_H

/* Host MMIO fixture configuration; vendor driver/header bytes remain real. */
#define HAL_MODULE_ENABLED
#define HAL_RCC_MODULE_ENABLED
#define HAL_DMA_MODULE_ENABLED
#define HAL_SD_MODULE_ENABLED
#define HAL_I2C_MODULE_ENABLED
#define HSE_VALUE 8000000U
#define HSI_VALUE 8000000U
#define LSE_VALUE 32768U
#define LSI_VALUE 40000U
#define HSE_STARTUP_TIMEOUT 100U
#define LSE_STARTUP_TIMEOUT 5000U
#define USE_HAL_SD_REGISTER_CALLBACKS 0U
#define USE_HAL_I2C_REGISTER_CALLBACKS 0U
#define USE_RTOS 0U
#define assert_param(expression_) ((void)0)

#include "stm32f1xx_hal_rcc.h"
#include "stm32f1xx_hal_dma.h"
#include "stm32f1xx_hal_sd.h"
#include "stm32f1xx_hal_i2c.h"

#endif /* __STM32F1XX_HAL_CONF_H */
