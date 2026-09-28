/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file           : main.h
  * @brief          : Header for main.c file.
  *                   This file contains the common defines of the application.
  ******************************************************************************
  * @attention
  *
  * Copyright (c) 2026 STMicroelectronics.
  * All rights reserved.
  *
  * This software is licensed under terms that can be found in the LICENSE file
  * in the root directory of this software component.
  * If no LICENSE file comes with this software, it is provided AS-IS.
  *
  ******************************************************************************
  */
/* USER CODE END Header */

/* Define to prevent recursive inclusion -------------------------------------*/
#ifndef __MAIN_H
#define __MAIN_H

#ifdef __cplusplus
extern "C" {
#endif

/* Includes ------------------------------------------------------------------*/
#include "stm32f4xx_hal.h"

/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */

/* USER CODE END Includes */

/* Exported types ------------------------------------------------------------*/
/* USER CODE BEGIN ET */

/* USER CODE END ET */

/* Exported constants --------------------------------------------------------*/
/* USER CODE BEGIN EC */

/* USER CODE END EC */

/* Exported macro ------------------------------------------------------------*/
/* USER CODE BEGIN EM */

/* USER CODE END EM */

/* Exported functions prototypes ---------------------------------------------*/
void Error_Handler(void);

/* USER CODE BEGIN EFP */

/* USER CODE END EFP */

/* Private defines -----------------------------------------------------------*/
#define GNSS_RST_Pin GPIO_PIN_5
#define GNSS_RST_GPIO_Port GPIOE
#define GNSS_TIMEPULSE_Pin GPIO_PIN_6
#define GNSS_TIMEPULSE_GPIO_Port GPIOE
#define GNSS_TIMEPULSE_EXTI_IRQn EXTI9_5_IRQn
#define ADC_Pin GPIO_PIN_0
#define ADC_GPIO_Port GPIOC
#define IMU_CAL_LED_Pin GPIO_PIN_1
#define IMU_CAL_LED_GPIO_Port GPIOA
#define RADIO_NSS_Pin GPIO_PIN_4
#define RADIO_NSS_GPIO_Port GPIOA
#define RADIO_SCK_Pin GPIO_PIN_5
#define RADIO_SCK_GPIO_Port GPIOA
#define RADIO_MISDO_Pin GPIO_PIN_6
#define RADIO_MISDO_GPIO_Port GPIOA
#define RADIO_MOSI_Pin GPIO_PIN_7
#define RADIO_MOSI_GPIO_Port GPIOA
#define RADIO_RST_Pin GPIO_PIN_0
#define RADIO_RST_GPIO_Port GPIOB
#define RADIO_BUSY_Pin GPIO_PIN_1
#define RADIO_BUSY_GPIO_Port GPIOB
#define RADIO_DIO1_Pin GPIO_PIN_7
#define RADIO_DIO1_GPIO_Port GPIOE
#define RADIO_DIO1_EXTI_IRQn EXTI9_5_IRQn
#define DBG_MT_Pin GPIO_PIN_10
#define DBG_MT_GPIO_Port GPIOB
#define DBG_MR_Pin GPIO_PIN_11
#define DBG_MR_GPIO_Port GPIOB
#define P_CONTROL2_Pin GPIO_PIN_14
#define P_CONTROL2_GPIO_Port GPIOB
#define P_CONTROL1_Pin GPIO_PIN_15
#define P_CONTROL1_GPIO_Port GPIOB
#define IMU_MT_Pin GPIO_PIN_9
#define IMU_MT_GPIO_Port GPIOA
#define IMU_MR_Pin GPIO_PIN_10
#define IMU_MR_GPIO_Port GPIOA
#define GNSS_MT_Pin GPIO_PIN_5
#define GNSS_MT_GPIO_Port GPIOD
#define GNSS_MR_Pin GPIO_PIN_6
#define GNSS_MR_GPIO_Port GPIOD

/* USER CODE BEGIN Private defines */

/* USER CODE END Private defines */

#ifdef __cplusplus
}
#endif

#endif /* __MAIN_H */
