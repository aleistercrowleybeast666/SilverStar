#ifndef __COMMON_FORMAT_H
#define __COMMON_FORMAT_H

#include <stdarg.h>
#include <stddef.h>
#include <stdint.h>

int32_t CommonFormat_Print(char *text, size_t capacity,
    const char *format, ...);
int32_t CommonFormat_VPrint(char *text, size_t capacity,
    const char *format, va_list arguments);

#endif /* __COMMON_FORMAT_H */
