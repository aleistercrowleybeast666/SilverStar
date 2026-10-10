#include "c071_context.h"
#include "main.h"
uint8_t C071MainContext_AllowedGet(void) { return ((__get_IPSR() == 0U) && (__get_PRIMASK() == 0U)) ? 1U : 0U; }
