#ifndef __NATIVE_NO_HEAP_H
#define __NATIVE_NO_HEAP_H
#include <stddef.h>
/* Fixed newlib syscall spelling; every request fails with ENOMEM. */
void *_sbrk(ptrdiff_t increment);
#endif /* __NATIVE_NO_HEAP_H */
