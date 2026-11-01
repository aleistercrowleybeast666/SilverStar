#include "native_no_heap.h"
#include <assert.h>
#include <stdint.h>
#include <errno.h>
int main(void)
{
    const ptrdiff_t requests[]={0,1,-1,PTRDIFF_MAX,PTRDIFF_MIN,1024,-1024};
    for (uint32_t index=0U;index<7U;index++)
    { errno=0;assert(_sbrk(requests[index])==(void *)-1 && errno==ENOMEM); }
    return 0;
}
