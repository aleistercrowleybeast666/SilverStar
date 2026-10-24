#include "usart.h"

/* Zero-initialized state must fail the real generated guard until the test
 * explicitly supplies matching configuration. No peripheral operations. */
HostUartHandle huart1, huart2, huart3, huart4, huart5, huart6;
