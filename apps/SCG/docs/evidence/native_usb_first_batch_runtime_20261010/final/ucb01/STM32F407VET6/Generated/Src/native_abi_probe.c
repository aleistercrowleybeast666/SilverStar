#include "main.h"
#include "usbd_cdc.h"
#include "usbd_cdc_if.h"
#include <stdint.h>
_Static_assert(__CORTEX_M == 4U, "native CMSIS Cortex must match independent device facts");
_Static_assert(__FPU_PRESENT == 1U, "independent FPU facts must match native CMSIS");
_Static_assert(sizeof(void *) == 4U, "selected native ABI must use 32-bit pointers");
_Static_assert(sizeof(((USBD_CDC_HandleTypeDef *)0)->TxState) == sizeof(uint32_t), "selected CDC adapter requires 32-bit TxState");
HAL_StatusTypeDef HAL_SPI_Transmit(SPI_HandleTypeDef *, const uint8_t *, uint16_t, uint32_t);
HAL_StatusTypeDef HAL_SPI_TransmitReceive(SPI_HandleTypeDef *, const uint8_t *, uint8_t *, uint16_t, uint32_t);
void HAL_GPIO_WritePin(GPIO_TypeDef *, uint16_t, GPIO_PinState);
GPIO_PinState HAL_GPIO_ReadPin(GPIO_TypeDef *, uint16_t);
uint32_t HAL_GetTick(void);
uint8_t CDC_Transmit_FS(uint8_t *, uint16_t);
