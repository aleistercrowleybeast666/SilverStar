#include "native_no_heap.h"
#include <errno.h>

void *_sbrk(ptrdiff_t increment)
{
    /* Newlib ABI requires this argument; it never grants capacity. */
    (void)increment;
    errno = ENOMEM;
    return (void *)-1;
}
