#include <math.h>
#include <stdint.h>
#include <string.h>

#include "common_format.h"
#include "test_common.h"

static void Test_IntegerAndTextFormat(void)
{
    char text[96];
    int32_t length;

    length = CommonFormat_Print(text, sizeof(text),
        "%s %u %ld %lu 0x%08lX 0x%02X", "VALUE", 7U, -12L, 34UL,
        0xA1B2C3D4UL, 0x5AU);
    TEST_CHECK(strcmp(text,
        "VALUE 7 -12 34 0xA1B2C3D4 0x5A") == 0);
    TEST_CHECK(length == (int32_t)strlen(text));

    length = CommonFormat_Print(text, sizeof(text), "[%5u][%-5s][%+ld]",
        12U, "OK", 3L);
    TEST_CHECK(strcmp(text, "[   12][OK   ][+3]") == 0);
    TEST_CHECK(length == (int32_t)strlen(text));
}

static void Test_FloatFormat(void)
{
    char text[128];

    (void)CommonFormat_Print(text, sizeof(text),
        "%.2f %.3f %.6f", 46.25, -1.25, 1.0);
    TEST_CHECK(strcmp(text, "46.25 -1.250 1.000000") == 0);

    (void)CommonFormat_Print(text, sizeof(text),
        "%.6g %.6g %.6g %.6g", 4.0, 0.25, 0.00001, 1000000.0);
    TEST_CHECK(strcmp(text, "4 0.25 1e-05 1e+06") == 0);

    (void)CommonFormat_Print(text, sizeof(text), "%.3f %.3f %.3f",
        -0.0, INFINITY, NAN);
    TEST_CHECK(strcmp(text, "-0.000 inf nan") == 0);
}

static void Test_Bounds(void)
{
    char text[5];

    TEST_CHECK(CommonFormat_Print(text, sizeof(text), "abcdef") == 6);
    TEST_CHECK(strcmp(text, "abcd") == 0);
    TEST_CHECK(CommonFormat_Print(NULL, 0U, "abc") == 3);
    TEST_CHECK(CommonFormat_Print(NULL, 1U, "abc") == -1);
}

static void Test_LongFormat(void)
{
    static const char format[] =
        "0000000000000000000000000000000000000000000000000000000000000000"
        "1111111111111111111111111111111111111111111111111111111111111111"
        "2222222222222222222222222222222222222222222222222222222222222222"
        "3333333333333333333333333333333333333333333333333333333333333333"
        " value=%lu";
    char text[320];

    TEST_CHECK(CommonFormat_Print(text, sizeof(text), format, 42UL) == 265);
    TEST_CHECK(strstr(text, "value=42") != NULL);
}

int main(void)
{
    Test_IntegerAndTextFormat();
    Test_FloatFormat();
    Test_Bounds();
    Test_LongFormat();
    return Test_Finish("common_format");
}
