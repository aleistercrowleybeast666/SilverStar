"""Replace the recognized native heap extender with a rejecting libc ABI.

Original sysmem bytes remain archived. No allocator is hidden or allowed: the
new compiled owner rejects every request, including initialization and zero.
"""
import hashlib


def NativeNoHeap_FilesRender(source: bytes) -> dict[str, bytes]:
    if hashlib.sha256(source).hexdigest() != 'ad20f7b1fa1e7c73330727747222cf2ffa3245ebf035230ee9a157545e79df95':
        raise ValueError('Native no-heap replacement requires reviewed sysmem source identity')
    return {
        'Generated/Inc/native_no_heap.h':b'''#ifndef __NATIVE_NO_HEAP_H
#define __NATIVE_NO_HEAP_H
#include <stddef.h>
/* Fixed newlib syscall spelling; every request fails with ENOMEM. */
void *_sbrk(ptrdiff_t increment);
#endif /* __NATIVE_NO_HEAP_H */
''',
        'Generated/Src/native_no_heap.c':b'''#include "native_no_heap.h"
#include <errno.h>

void *_sbrk(ptrdiff_t increment)
{
    /* Newlib ABI requires this argument; it never grants capacity. */
    (void)increment;
    errno = ENOMEM;
    return (void *)-1;
}
'''}
