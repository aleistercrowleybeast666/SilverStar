#include <assert.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
typedef enum { HAL_OK, HAL_ERROR, HAL_BUSY, HAL_TIMEOUT } HAL_StatusTypeDef;
typedef struct { uint32_t DR; } UartRegisters;
typedef struct { uint32_t WordLength, Parity; } UartInit;
typedef struct {
    UartRegisters *Instance; UartInit Init;
    uint32_t gState, RxState, ErrorCode, ReceptionType, RxEventType;
    uint16_t TxXferSize, TxXferCount, RxXferSize, RxXferCount;
} UART_HandleTypeDef;
#define HAL_UART_STATE_READY 1U
#define HAL_UART_STATE_BUSY_TX 2U
#define HAL_UART_STATE_BUSY_RX 3U
#define HAL_UART_ERROR_NONE 0U
#define HAL_UART_RECEPTION_TOIDLE 1U
#define HAL_UART_RXEVENT_TC 1U
#define HAL_UART_RXEVENT_IDLE 2U
#define UART_WORDLENGTH_8B 8U
#define UART_WORDLENGTH_9B 9U
#define UART_PARITY_NONE 0U
#define UART_FLAG_TXE 1U
#define UART_FLAG_TC 2U
#define UART_FLAG_IDLE 3U
#define UART_FLAG_RXNE 4U
#define HAL_MAX_DELAY UINT32_MAX
#define RESET 0U
static uint32_t native_tick, rx_enabled=1U;
static HAL_StatusTypeDef wait_result=HAL_OK;
static uint32_t HAL_GetTick(void) { return native_tick++; }
static HAL_StatusTypeDef UART_WaitOnFlagUntilTimeout(UART_HandleTypeDef *h,
    uint32_t flag, uint32_t state, uint32_t tick, uint32_t timeout)
{ (void)h; (void)flag; (void)state; (void)tick; (void)timeout; return wait_result; }
#define __HAL_UART_GET_FLAG(h,f) ((void)(h), ((f)==UART_FLAG_RXNE ? rx_enabled : 0U))
#define __HAL_UART_CLEAR_IDLEFLAG(h) ((void)(h))
HAL_StatusTypeDef HAL_UART_Transmit(UART_HandleTypeDef *huart, const uint8_t *pData, uint16_t Size, uint32_t Timeout)
{
  const uint8_t  *pdata8bits;
  const uint16_t *pdata16bits;
  uint32_t tickstart = 0U;

  /* Check that a Tx process is not already ongoing */
  if (huart->gState == HAL_UART_STATE_READY)
  {
    if ((pData == NULL) || (Size == 0U))
    {
      return  HAL_ERROR;
    }

    huart->ErrorCode = HAL_UART_ERROR_NONE;
    huart->gState = HAL_UART_STATE_BUSY_TX;

    /* Init tickstart for timeout management */
    tickstart = HAL_GetTick();

    huart->TxXferSize = Size;
    huart->TxXferCount = Size;

    /* In case of 9bits/No Parity transfer, pData needs to be handled as a uint16_t pointer */
    if ((huart->Init.WordLength == UART_WORDLENGTH_9B) && (huart->Init.Parity == UART_PARITY_NONE))
    {
      pdata8bits  = NULL;
      pdata16bits = (const uint16_t *) pData;
    }
    else
    {
      pdata8bits  = pData;
      pdata16bits = NULL;
    }

    while (huart->TxXferCount > 0U)
    {
      if (UART_WaitOnFlagUntilTimeout(huart, UART_FLAG_TXE, RESET, tickstart, Timeout) != HAL_OK)
      {
        huart->gState = HAL_UART_STATE_READY;

        return HAL_TIMEOUT;
      }
      if (pdata8bits == NULL)
      {
        huart->Instance->DR = (uint16_t)(*pdata16bits & 0x01FFU);
        pdata16bits++;
      }
      else
      {
        huart->Instance->DR = (uint8_t)(*pdata8bits & 0xFFU);
        pdata8bits++;
      }
      huart->TxXferCount--;
    }

    if (UART_WaitOnFlagUntilTimeout(huart, UART_FLAG_TC, RESET, tickstart, Timeout) != HAL_OK)
    {
      huart->gState = HAL_UART_STATE_READY;

      return HAL_TIMEOUT;
    }

    /* At end of Tx process, restore huart->gState to Ready */
    huart->gState = HAL_UART_STATE_READY;

    return HAL_OK;
  }
  else
  {
    return HAL_BUSY;
  }
}
HAL_StatusTypeDef HAL_UARTEx_ReceiveToIdle(UART_HandleTypeDef *huart, uint8_t *pData, uint16_t Size, uint16_t *RxLen,
                                           uint32_t Timeout)
{
  uint8_t  *pdata8bits;
  uint16_t *pdata16bits;
  uint32_t tickstart;

  /* Check that a Rx process is not already ongoing */
  if (huart->RxState == HAL_UART_STATE_READY)
  {
    if ((pData == NULL) || (Size == 0U))
    {
      return  HAL_ERROR;
    }

    huart->ErrorCode = HAL_UART_ERROR_NONE;
    huart->RxState = HAL_UART_STATE_BUSY_RX;
    huart->ReceptionType = HAL_UART_RECEPTION_TOIDLE;
    huart->RxEventType = HAL_UART_RXEVENT_TC;

    /* Init tickstart for timeout management */
    tickstart = HAL_GetTick();

    huart->RxXferSize  = Size;
    huart->RxXferCount = Size;

    /* In case of 9bits/No Parity transfer, pRxData needs to be handled as a uint16_t pointer */
    if ((huart->Init.WordLength == UART_WORDLENGTH_9B) && (huart->Init.Parity == UART_PARITY_NONE))
    {
      pdata8bits  = NULL;
      pdata16bits = (uint16_t *) pData;
    }
    else
    {
      pdata8bits  = pData;
      pdata16bits = NULL;
    }

    /* Initialize output number of received elements */
    *RxLen = 0U;

    /* as long as data have to be received */
    while (huart->RxXferCount > 0U)
    {
      /* Check if IDLE flag is set */
      if (__HAL_UART_GET_FLAG(huart, UART_FLAG_IDLE))
      {
        /* Clear IDLE flag in ISR */
        __HAL_UART_CLEAR_IDLEFLAG(huart);

        /* If Set, but no data ever received, clear flag without exiting loop */
        /* If Set, and data has already been received, this means Idle Event is valid : End reception */
        if (*RxLen > 0U)
        {
          huart->RxEventType = HAL_UART_RXEVENT_IDLE;
          huart->RxState = HAL_UART_STATE_READY;

          return HAL_OK;
        }
      }

      /* Check if RXNE flag is set */
      if (__HAL_UART_GET_FLAG(huart, UART_FLAG_RXNE))
      {
        if (pdata8bits == NULL)
        {
          *pdata16bits = (uint16_t)(huart->Instance->DR & (uint16_t)0x01FF);
          pdata16bits++;
        }
        else
        {
          if ((huart->Init.WordLength == UART_WORDLENGTH_9B) || ((huart->Init.WordLength == UART_WORDLENGTH_8B) && (huart->Init.Parity == UART_PARITY_NONE)))
          {
            *pdata8bits = (uint8_t)(huart->Instance->DR & (uint8_t)0x00FF);
          }
          else
          {
            *pdata8bits = (uint8_t)(huart->Instance->DR & (uint8_t)0x007F);
          }

          pdata8bits++;
        }
        /* Increment number of received elements */
        *RxLen += 1U;
        huart->RxXferCount--;
      }

      /* Check for the Timeout */
      if (Timeout != HAL_MAX_DELAY)
      {
        if (((HAL_GetTick() - tickstart) > Timeout) || (Timeout == 0U))
        {
          huart->RxState = HAL_UART_STATE_READY;

          return HAL_TIMEOUT;
        }
      }
    }

    /* Set number of received elements in output parameter : RxLen */
    *RxLen = huart->RxXferSize - huart->RxXferCount;
    /* At end of Rx process, restore huart->RxState to Ready */
    huart->RxState = HAL_UART_STATE_READY;

    return HAL_OK;
  }
  else
  {
    return HAL_BUSY;
  }
}
static uint16_t buffer[65537];
int main(int argc, char **argv)
{
    UartRegisters registers={0U};
    UART_HandleTypeDef uart={.Instance=&registers,
        .Init={UART_WORDLENGTH_8B,UART_PARITY_NONE},
        .gState=HAL_UART_STATE_READY,.RxState=HAL_UART_STATE_READY};
    assert(argc==2);
    if (strcmp(argv[1],"fault-tx")==0 || strcmp(argv[1],"fault-rx")==0)
    {
        uint16_t received=0U;
        uart.Init.WordLength=UART_WORDLENGTH_9B;
        if (strcmp(argv[1],"fault-tx")==0)
        { assert(HAL_UART_Transmit(&uart,(uint8_t *)&buffer[1],1U,100U)==HAL_ERROR);
          assert(uart.gState==HAL_UART_STATE_READY && registers.DR==0U); }
        else
        { assert(HAL_UARTEx_ReceiveToIdle(&uart,(uint8_t *)&buffer[1],1U,&received,100U)==HAL_ERROR);
          assert(uart.RxState==HAL_UART_STATE_READY && received==0U); }
        return 0;
    }
    const uint16_t sizes[]={1U,3U,65535U};
    for (uint32_t mode=0U;mode<2U;mode++)
    {
        uart.Init.WordLength=mode==0U ? UART_WORDLENGTH_8B : UART_WORDLENGTH_9B;
        for (uint32_t item=0U;item<3U;item++)
        {
            uint16_t received=0U;
            uint16_t size=sizes[item];
            buffer[0]=0xCAFEU; buffer[65536]=0xBEEFU;
            for (uint32_t i=1U;i<65536U;i++) { buffer[i]=0x01A5U; }
            uint16_t expected=mode==0U ? ((uint8_t *)&buffer[1])[size-1U] : buffer[size];
            assert(HAL_UART_Transmit(&uart,(uint8_t *)&buffer[1],size,HAL_MAX_DELAY)==HAL_OK);
            assert(registers.DR==expected && uart.TxXferCount==0U && uart.gState==HAL_UART_STATE_READY);
            registers.DR=0x1A5U;
            assert(HAL_UARTEx_ReceiveToIdle(&uart,(uint8_t *)&buffer[1],size,&received,HAL_MAX_DELAY)==HAL_OK);
            assert(received==size && uart.RxXferCount==0U && uart.RxState==HAL_UART_STATE_READY);
            assert((mode==0U ? ((uint8_t *)&buffer[1])[size-1U] : buffer[size])==(mode==0U ? 0xA5U : 0x1A5U));
            assert(buffer[0]==0xCAFEU && buffer[65536]==0xBEEFU);
        }
    }
    uint16_t received=0xABCDU;
    assert(HAL_UART_Transmit(&uart,NULL,1U,1U)==HAL_ERROR);
    assert(HAL_UART_Transmit(&uart,(uint8_t *)buffer,0U,1U)==HAL_ERROR);
    assert(HAL_UARTEx_ReceiveToIdle(&uart,NULL,1U,&received,1U)==HAL_ERROR && received==0xABCDU);
    wait_result=HAL_TIMEOUT;
    assert(HAL_UART_Transmit(&uart,(uint8_t *)buffer,1U,1U)==HAL_TIMEOUT && uart.gState==HAL_UART_STATE_READY);
    rx_enabled=0U;
    assert(HAL_UARTEx_ReceiveToIdle(&uart,(uint8_t *)buffer,1U,&received,0U)==HAL_TIMEOUT);
    assert(received==0U && uart.RxState==HAL_UART_STATE_READY);
    return 0;
}
