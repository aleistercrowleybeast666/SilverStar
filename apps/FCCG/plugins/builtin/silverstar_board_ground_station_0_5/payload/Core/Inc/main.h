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
#include "stm32f1xx_hal.h"

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
#define LED_Pin GPIO_PIN_13
#define LED_GPIO_Port GPIOC
#define SPI_RADIO_NSS_Pin GPIO_PIN_4
#define SPI_RADIO_NSS_GPIO_Port GPIOA
#define SPI_RADIO_SCK_Pin GPIO_PIN_5
#define SPI_RADIO_SCK_GPIO_Port GPIOA
#define SPI_RADIO_MISO_Pin GPIO_PIN_6
#define SPI_RADIO_MISO_GPIO_Port GPIOA
#define SPI_RADIO_MOSI_Pin GPIO_PIN_7
#define SPI_RADIO_MOSI_GPIO_Port GPIOA
#define RADIO_DIO1_Pin GPIO_PIN_0
#define RADIO_DIO1_GPIO_Port GPIOB
#define RADIO_DIO1_EXTI_IRQn EXTI0_IRQn
#define RADIO_DIO2_Pin GPIO_PIN_1
#define RADIO_DIO2_GPIO_Port GPIOB
#define RADIO_BUSY_Pin GPIO_PIN_10
#define RADIO_BUSY_GPIO_Port GPIOB
#define RADIO_RST_Pin GPIO_PIN_11
#define RADIO_RST_GPIO_Port GPIOB
#define UART_EXT_MT_Pin GPIO_PIN_9
#define UART_EXT_MT_GPIO_Port GPIOA
#define UART_EXT_MR_Pin GPIO_PIN_10
#define UART_EXT_MR_GPIO_Port GPIOA
#define RADIO_DIO3_Pin GPIO_PIN_3
#define RADIO_DIO3_GPIO_Port GPIOB

/* USER CODE BEGIN Private defines */

/* USER CODE END Private defines */

#ifdef __cplusplus
}
#endif

#endif /* __MAIN_H */
