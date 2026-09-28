#include "platform_adc.h"

#include "platform_stm32f4_resources.h"
#include "silverstar_assert.h"
#include "stm32f4xx_hal.h"

PlatformResult PlatformAdc_Read(PlatformAdcId id,
                                uint32_t timeout_ms,
                                uint32_t *raw_count)
{
    ADC_HandleTypeDef *handle;
    HAL_StatusTypeDef result;

    handle = (ADC_HandleTypeDef *)
        PlatformStm32f4Resource_AdcHandleGet(id);
    if ((handle == NULL) || (raw_count == NULL))
    {
        return PLATFORM_INVALID_ARGUMENT;
    }
    SILVERSTAR_ASSERT_OBJECT(raw_count, uint32_t,
                             SILVERSTAR_ASSERT_MODULE_PLATFORM);
    result = HAL_ADC_Start(handle);
    if (result != HAL_OK) { return PLATFORM_IO_ERROR; }
    result = HAL_ADC_PollForConversion(handle, timeout_ms);
    if (result != HAL_OK)
    {
        (void)HAL_ADC_Stop(handle);
        return (result == HAL_TIMEOUT) ? PLATFORM_TIMEOUT : PLATFORM_IO_ERROR;
    }
    *raw_count = HAL_ADC_GetValue(handle);
    (void)HAL_ADC_Stop(handle);
    return PLATFORM_OK;
}
