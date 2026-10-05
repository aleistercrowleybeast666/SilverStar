#ifndef __STM32F4XX_HAL_H
#define __STM32F4XX_HAL_H

#include <stdint.h>

typedef enum
{
    HAL_OK = 0,
    HAL_ERROR,
    HAL_BUSY,
    HAL_TIMEOUT
} HAL_StatusTypeDef;

typedef struct { uint32_t marker; } I2C_HandleTypeDef;
typedef struct { uint32_t marker; } CAN_HandleTypeDef;
typedef struct { uint32_t Period; } TIM_Base_InitTypeDef;
typedef struct { uint32_t CCMR1; uint32_t CCMR2; } TIM_TypeDef;
typedef struct { TIM_TypeDef *Instance; TIM_Base_InitTypeDef Init; } TIM_HandleTypeDef;

typedef struct
{
    uint32_t StdId;
    uint32_t ExtId;
    uint32_t IDE;
    uint32_t RTR;
    uint32_t DLC;
} CAN_TxHeaderTypeDef;

typedef CAN_TxHeaderTypeDef CAN_RxHeaderTypeDef;

#define I2C_MEMADD_SIZE_8BIT  1U
#define I2C_MEMADD_SIZE_16BIT 2U
#define CAN_ID_STD             0U
#define CAN_ID_EXT             1U
#define CAN_RTR_DATA           0U
#define CAN_RX_FIFO0           0U
#define HAL_CAN_ERROR_BOF      (1UL << 0U)
#define HAL_CAN_ERROR_RX_FOV0  (1UL << 1U)
#define TIM_CHANNEL_1          0x00000000U
#define TIM_CHANNEL_2          0x00000004U
#define TIM_CHANNEL_3          0x00000008U
#define TIM_CHANNEL_4          0x0000000CU
#define TIM_CCMR1_OC1M         0x00000070U
#define TIM_CCMR1_OC2M         0x00007000U
#define TIM_CCMR2_OC3M         0x00000070U
#define TIM_CCMR2_OC4M         0x00007000U
#define TIM_OCMODE_PWM1        0x00000060U
#define TIM_OCMODE_PWM2        0x00000070U
#define TIM_OCMODE_FORCED_ACTIVE   0x00000050U
#define TIM_OCMODE_FORCED_INACTIVE 0x00000040U
#define MODIFY_REG(REG, CLEARMASK, SETMASK) \
    ((REG) = (((REG) & ~(CLEARMASK)) | (SETMASK)))

HAL_StatusTypeDef HAL_I2C_Master_Transmit(
    I2C_HandleTypeDef *handle, uint16_t address, uint8_t *data,
    uint16_t length, uint32_t timeout_ms);
HAL_StatusTypeDef HAL_I2C_Master_Receive(
    I2C_HandleTypeDef *handle, uint16_t address, uint8_t *data,
    uint16_t length, uint32_t timeout_ms);
HAL_StatusTypeDef HAL_I2C_Mem_Write(
    I2C_HandleTypeDef *handle, uint16_t address, uint16_t memory_address,
    uint16_t memory_address_size, uint8_t *data, uint16_t length,
    uint32_t timeout_ms);
HAL_StatusTypeDef HAL_I2C_Mem_Read(
    I2C_HandleTypeDef *handle, uint16_t address, uint16_t memory_address,
    uint16_t memory_address_size, uint8_t *data, uint16_t length,
    uint32_t timeout_ms);

HAL_StatusTypeDef HAL_CAN_Start(CAN_HandleTypeDef *handle);
HAL_StatusTypeDef HAL_CAN_Stop(CAN_HandleTypeDef *handle);
uint32_t HAL_CAN_GetError(CAN_HandleTypeDef *handle);
uint32_t HAL_CAN_GetTxMailboxesFreeLevel(CAN_HandleTypeDef *handle);
HAL_StatusTypeDef HAL_CAN_AddTxMessage(
    CAN_HandleTypeDef *handle, CAN_TxHeaderTypeDef *header,
    uint8_t *data, uint32_t *mailbox);
uint32_t HAL_CAN_GetRxFifoFillLevel(
    CAN_HandleTypeDef *handle, uint32_t fifo);
HAL_StatusTypeDef HAL_CAN_GetRxMessage(
    CAN_HandleTypeDef *handle, uint32_t fifo,
    CAN_RxHeaderTypeDef *header, uint8_t *data);
uint32_t HAL_GetTick(void);

HAL_StatusTypeDef HAL_TIM_PWM_Start(
    TIM_HandleTypeDef *handle, uint32_t channel);
HAL_StatusTypeDef HAL_TIM_PWM_Stop(
    TIM_HandleTypeDef *handle, uint32_t channel);
void TestHal_TimCompareSet(
    TIM_HandleTypeDef *handle, uint32_t channel, uint32_t compare);
#define __HAL_TIM_SET_COMPARE(handle, channel, compare) \
    TestHal_TimCompareSet((handle), (channel), (compare))

#endif /* __STM32F4XX_HAL_H */
