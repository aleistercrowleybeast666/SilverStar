#ifndef HOST_MAIN_H
#define HOST_MAIN_H
#include <stdint.h>
typedef enum { HAL_OK,HAL_ERROR,HAL_BUSY,HAL_TIMEOUT } HAL_StatusTypeDef;
typedef enum { GPIO_PIN_RESET,GPIO_PIN_SET } GPIO_PinState;
typedef struct { uint32_t value; } GPIO_TypeDef;
typedef struct { uint32_t Mode,Direction,DataSize,CLKPolarity,CLKPhase,NSS,FirstBit,TIMode,CRCCalculation,BaudRatePrescaler; } SpiInit;
typedef struct { void *Instance; SpiInit Init; uint32_t State; } SPI_HandleTypeDef;
extern GPIO_TypeDef gpioa,gpiob;
#define GPIOA (&gpioa)
#define GPIOB (&gpiob)
#define SPI1 ((void *)GPIOA)
#define GPIO_PIN_4 16U
#define GPIO_PIN_11 2048U
#define GPIO_PIN_10 1024U
#define GPIO_PIN_0 1U
#define SPI_MODE_MASTER 1U
#define SPI_DIRECTION_2LINES 1U
#define SPI_DATASIZE_8BIT 1U
#define SPI_POLARITY_LOW 1U
#define SPI_PHASE_1EDGE 1U
#define SPI_NSS_SOFT 1U
#define SPI_FIRSTBIT_MSB 1U
#define SPI_TIMODE_DISABLE 1U
#define SPI_CRCCALCULATION_DISABLE 1U
#define SPI_BAUDRATEPRESCALER_8 1U
#define HAL_SPI_STATE_READY 1U
uint32_t __get_IPSR(void);
uint32_t __get_PRIMASK(void);
void HAL_GPIO_EXTI_Callback(uint16_t pin);
void HAL_GPIO_WritePin(GPIO_TypeDef *,uint16_t,GPIO_PinState);
GPIO_PinState HAL_GPIO_ReadPin(GPIO_TypeDef *,uint16_t);
HAL_StatusTypeDef HAL_SPI_Transmit(SPI_HandleTypeDef *,uint8_t *,uint16_t,uint32_t);
HAL_StatusTypeDef HAL_SPI_TransmitReceive(SPI_HandleTypeDef *,uint8_t *,uint8_t *,uint16_t,uint32_t);
#endif
