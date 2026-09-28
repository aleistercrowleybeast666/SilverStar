#ifndef __TEST_COMMON_H
#define __TEST_COMMON_H

#include <math.h>
#include <stdio.h>

static int s_test_checks;
static int s_test_failures;

#define TEST_CHECK(condition_) \
    do \
    { \
        s_test_checks++; \
        if (!(condition_)) \
        { \
            s_test_failures++; \
            (void)printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #condition_); \
        } \
    } while (0)

#define TEST_CHECK_NEAR(actual_, expected_, tolerance_) \
    TEST_CHECK(fabsf((actual_) - (expected_)) <= (tolerance_))

static int Test_Finish(const char *name)
{
    (void)printf("%s: %d checks, %d failures\n",
                 name, s_test_checks, s_test_failures);
    return (s_test_failures == 0) ? 0 : 1;
}

#endif /* __TEST_COMMON_H */
