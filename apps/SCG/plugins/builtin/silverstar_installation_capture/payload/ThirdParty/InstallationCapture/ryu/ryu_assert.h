/* SilverStar integration bridge; upstream Ryu licenses remain in this directory.
 * Internal Ryu preconditions use the established bounded target fail-stop.
 * Invalid external numbers are rejected before entering Ryu. */
#ifndef __RYU_ASSERT_H
#define __RYU_ASSERT_H

#include "silverstar_assert.h"

#define RYU_ASSERT(expression_) \
    ((expression_) ? (void)0 : SilverStarAssert_Fail( \
        SILVERSTAR_ASSERT_MODULE_MODULES, __FILE__, (uint32_t)__LINE__, \
        SILVERSTAR_ASSERT_REASON_STATE_INVARIANT))

#endif /* __RYU_ASSERT_H */
