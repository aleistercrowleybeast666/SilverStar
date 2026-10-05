#include "common_format.h"

#include <limits.h>
#include <math.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>

#include "silverstar_assert.h"

#define COMMON_FORMAT_FIELD_CAPACITY              96U
#define COMMON_FORMAT_MAX_FLOAT_PRECISION          9U
#define COMMON_FORMAT_MAX_FORMAT_LENGTH         3072U
#define COMMON_FORMAT_MAX_TEXT_LENGTH           1024U
#define COMMON_FORMAT_MAX_FIELD_WIDTH           1024U
#define COMMON_FORMAT_MAX_INTEGER_DIGITS          32U
#define COMMON_FORMAT_MAX_FLAG_CHARACTERS          5U
#define COMMON_FORMAT_MAX_WIDTH_DIGITS             5U
#define COMMON_FORMAT_MAX_PRECISION_DIGITS         3U
#define COMMON_FORMAT_MAX_PRECISION               96U
#define COMMON_FORMAT_MAX_EXPONENT_ADJUSTMENTS    400U

typedef enum
{
    COMMON_FORMAT_LENGTH_DEFAULT = 0,
    COMMON_FORMAT_LENGTH_LONG,
    COMMON_FORMAT_LENGTH_LONG_LONG,
    COMMON_FORMAT_LENGTH_SIZE
} CommonFormatLength;

typedef struct
{
    char *text;
    size_t capacity;
    size_t length;
} CommonFormatBuffer;

typedef struct
{
    const char *cursor;
    size_t remaining;
} CommonFormatParser;

typedef struct
{
    size_t width;
    int32_t precision;
    CommonFormatLength length;
    char conversion;
    bool left_aligned;
    bool zero_padded;
    bool positive_sign;
    bool space_sign;
    bool alternate_form;
} CommonFormatSpec;

static void CommonFormat_CharacterPut(CommonFormatBuffer *buffer,
                                      char character)
{
    SILVERSTAR_ASSERT(buffer != NULL, SILVERSTAR_ASSERT_MODULE_COMMON,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    if ((buffer->text != NULL) && (buffer->capacity != 0U) &&
        (buffer->length < (buffer->capacity - 1U)))
    {
        buffer->text[buffer->length] = character;
    }
    if (buffer->length < SIZE_MAX) { buffer->length++; }
}

static void CommonFormat_TextPut(CommonFormatBuffer *buffer,
                                 const char *text,
                                 size_t length)
{
    size_t index;

    SILVERSTAR_ASSERT(buffer != NULL, SILVERSTAR_ASSERT_MODULE_COMMON,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT((text != NULL) &&
                      (length <= COMMON_FORMAT_MAX_TEXT_LENGTH),
                      SILVERSTAR_ASSERT_MODULE_COMMON,
                      SILVERSTAR_ASSERT_REASON_LENGTH_RANGE);
    for (index = 0U;
         (index < length) && (index < COMMON_FORMAT_MAX_TEXT_LENGTH);
         index++)
    {
        CommonFormat_CharacterPut(buffer, text[index]);
    }
}

static void CommonFormat_RepeatPut(CommonFormatBuffer *buffer,
                                   char character,
                                   size_t count)
{
    size_t index;

    SILVERSTAR_ASSERT(count <= COMMON_FORMAT_MAX_FIELD_WIDTH,
                      SILVERSTAR_ASSERT_MODULE_COMMON,
                      SILVERSTAR_ASSERT_REASON_LENGTH_RANGE);
    for (index = 0U;
         (index < count) && (index < COMMON_FORMAT_MAX_FIELD_WIDTH);
         index++)
    {
        CommonFormat_CharacterPut(buffer, character);
    }
}

static char CommonFormat_ParserCurrent(const CommonFormatParser *parser)
{
    if ((parser == NULL) || (parser->cursor == NULL) ||
        (parser->remaining == 0U))
    {
        return '\0';
    }
    return parser->cursor[0];
}

static void CommonFormat_ParserAdvance(CommonFormatParser *parser)
{
    SILVERSTAR_ASSERT((parser != NULL) && (parser->cursor != NULL),
                      SILVERSTAR_ASSERT_MODULE_COMMON,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    if (parser->remaining != 0U)
    {
        parser->cursor++;
        parser->remaining--;
    }
}

static size_t CommonFormat_UnsignedCreate(char *text,
                                          uint64_t value,
                                          uint32_t radix,
                                          bool uppercase)
{
    static const char s_lower_digits[] = "0123456789abcdef";
    static const char s_upper_digits[] = "0123456789ABCDEF";
    const char *digits = uppercase ? s_upper_digits : s_lower_digits;
    char reverse[COMMON_FORMAT_MAX_INTEGER_DIGITS];
    size_t length = 0U;
    size_t index;

    SILVERSTAR_ASSERT(text != NULL, SILVERSTAR_ASSERT_MODULE_COMMON,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT((radix >= 2U) && (radix <= 16U),
                      SILVERSTAR_ASSERT_MODULE_COMMON,
                      SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    for (index = 0U; index < COMMON_FORMAT_MAX_INTEGER_DIGITS; index++)
    {
        reverse[length] = digits[(size_t)(value % (uint64_t)radix)];
        length++;
        value /= (uint64_t)radix;
        if (value == 0U) { break; }
    }
    SILVERSTAR_ASSERT(value == 0U, SILVERSTAR_ASSERT_MODULE_COMMON,
                      SILVERSTAR_ASSERT_REASON_LOOP_BOUND);
    for (index = 0U; index < length; index++)
    {
        text[index] = reverse[length - index - 1U];
    }
    return length;
}

static void CommonFormat_FieldPut(CommonFormatBuffer *buffer,
                                  const char *field,
                                  size_t field_length,
                                  const CommonFormatSpec *spec,
                                  char padding)
{
    size_t padding_length = 0U;

    SILVERSTAR_ASSERT((buffer != NULL) && (field != NULL) && (spec != NULL),
                      SILVERSTAR_ASSERT_MODULE_COMMON,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT((field_length <= COMMON_FORMAT_MAX_TEXT_LENGTH) &&
                      (spec->width <= COMMON_FORMAT_MAX_FIELD_WIDTH),
                      SILVERSTAR_ASSERT_MODULE_COMMON,
                      SILVERSTAR_ASSERT_REASON_LENGTH_RANGE);
    if (spec->width > field_length)
    {
        padding_length = spec->width - field_length;
    }
    if (!spec->left_aligned)
    {
        CommonFormat_RepeatPut(buffer, padding, padding_length);
    }
    CommonFormat_TextPut(buffer, field, field_length);
    if (spec->left_aligned)
    {
        CommonFormat_RepeatPut(buffer, ' ', padding_length);
    }
}

static size_t CommonFormat_NumberLeadingZeroesGet(size_t digit_count,
                                                   int32_t precision)
{
    if ((precision >= 0) && ((size_t)precision > digit_count))
    {
        return (size_t)precision - digit_count;
    }
    return 0U;
}

static void CommonFormat_NumberPut(CommonFormatBuffer *buffer,
                                   const char *digits,
                                   size_t digit_count,
                                   char sign,
                                   const char *prefix,
                                   size_t prefix_length,
                                   const CommonFormatSpec *spec)
{
    size_t leading_zero_count;
    size_t field_length;
    size_t width_padding = 0U;

    SILVERSTAR_ASSERT((buffer != NULL) && (digits != NULL) &&
                      (prefix != NULL) && (spec != NULL),
                      SILVERSTAR_ASSERT_MODULE_COMMON,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(digit_count <= COMMON_FORMAT_MAX_INTEGER_DIGITS,
                      SILVERSTAR_ASSERT_MODULE_COMMON,
                      SILVERSTAR_ASSERT_REASON_LENGTH_RANGE);
    leading_zero_count = CommonFormat_NumberLeadingZeroesGet(
        digit_count, spec->precision);
    field_length = digit_count + leading_zero_count + prefix_length +
        ((sign != '\0') ? 1U : 0U);
    if (spec->width > field_length)
    {
        width_padding = spec->width - field_length;
    }
    if ((!spec->left_aligned) &&
        ((!spec->zero_padded) || (spec->precision >= 0)))
    {
        CommonFormat_RepeatPut(buffer, ' ', width_padding);
        width_padding = 0U;
    }
    if (sign != '\0') { CommonFormat_CharacterPut(buffer, sign); }
    CommonFormat_TextPut(buffer, prefix, prefix_length);
    if ((!spec->left_aligned) && spec->zero_padded &&
        (spec->precision < 0))
    {
        CommonFormat_RepeatPut(buffer, '0', width_padding);
        width_padding = 0U;
    }
    CommonFormat_RepeatPut(buffer, '0', leading_zero_count);
    CommonFormat_TextPut(buffer, digits, digit_count);
    if (spec->left_aligned)
    {
        CommonFormat_RepeatPut(buffer, ' ', width_padding);
    }
}

static uint64_t CommonFormat_Power10Get(uint32_t exponent)
{
    uint64_t value = 1U;
    uint32_t index;

    SILVERSTAR_ASSERT(exponent <= COMMON_FORMAT_MAX_FLOAT_PRECISION,
                      SILVERSTAR_ASSERT_MODULE_COMMON,
                      SILVERSTAR_ASSERT_REASON_LENGTH_RANGE);
    for (index = 0U;
         (index < exponent) &&
         (index < COMMON_FORMAT_MAX_FLOAT_PRECISION);
         index++)
    {
        value *= 10U;
    }
    return value;
}

static size_t CommonFormat_TrailingZeroesTrim(char *text, size_t length)
{
    uint32_t adjustment;

    for (adjustment = 0U;
         adjustment < COMMON_FORMAT_MAX_FLOAT_PRECISION;
         adjustment++)
    {
        if ((length == 0U) || (text[length - 1U] != '0')) { break; }
        length--;
    }
    if ((length != 0U) && (text[length - 1U] == '.')) { length--; }
    return length;
}

static size_t CommonFormat_FractionCreate(char *text,
                                          uint64_t fractional,
                                          uint32_t precision)
{
    size_t length = 0U;
    uint32_t index;

    for (index = 0U;
         (index < precision) &&
         (index < COMMON_FORMAT_MAX_FLOAT_PRECISION);
         index++)
    {
        const uint64_t divisor = CommonFormat_Power10Get(
            precision - index - 1U);
        const uint64_t digit = (fractional / divisor) % 10U;

        text[length] = (char)('0' + (char)digit);
        length++;
    }
    return length;
}

static size_t CommonFormat_FixedCreate(char *text,
                                       double value,
                                       uint32_t precision,
                                       bool trim_trailing_zeroes)
{
    const uint32_t bounded_precision =
        (precision > COMMON_FORMAT_MAX_FLOAT_PRECISION) ?
            COMMON_FORMAT_MAX_FLOAT_PRECISION : precision;
    const uint64_t scale = CommonFormat_Power10Get(bounded_precision);
    const double integral_value = floor(value);
    uint64_t integral;
    uint64_t fractional;
    size_t length;

    SILVERSTAR_ASSERT_OBJECT(text, char, SILVERSTAR_ASSERT_MODULE_COMMON);
    if (integral_value >= (double)UINT64_MAX) { return 0U; }
    integral = (uint64_t)integral_value;
    fractional = (uint64_t)floor(
        ((value - integral_value) * (double)scale) + 0.5);
    if (fractional >= scale) { fractional = 0U; integral++; }
    length = CommonFormat_UnsignedCreate(text, integral, 10U, false);
    if (bounded_precision != 0U)
    {
        text[length] = '.';
        length++;
        length += CommonFormat_FractionCreate(
            &text[length], fractional, bounded_precision);
    }
    return (trim_trailing_zeroes && (bounded_precision != 0U)) ?
        CommonFormat_TrailingZeroesTrim(text, length) : length;
}

static int32_t CommonFormat_DecimalExponentGet(double value,
                                                double *normalized)
{
    double normalized_value = value;
    int32_t exponent = 0;
    uint32_t adjustment;

    SILVERSTAR_ASSERT((normalized != NULL) && isfinite(value) &&
                      (value > 0.0),
                      SILVERSTAR_ASSERT_MODULE_COMMON,
                      SILVERSTAR_ASSERT_REASON_FLOAT_NOT_FINITE);
    for (adjustment = 0U;
         adjustment < COMMON_FORMAT_MAX_EXPONENT_ADJUSTMENTS;
         adjustment++)
    {
        if (normalized_value >= 10.0)
        {
            normalized_value /= 10.0;
            exponent++;
        }
        else if (normalized_value < 1.0)
        {
            normalized_value *= 10.0;
            exponent--;
        }
        else { break; }
    }
    SILVERSTAR_ASSERT((normalized_value >= 1.0) &&
                      (normalized_value < 10.0),
                      SILVERSTAR_ASSERT_MODULE_COMMON,
                      SILVERSTAR_ASSERT_REASON_LOOP_BOUND);
    *normalized = normalized_value;
    return exponent;
}

static size_t CommonFormat_ExponentAppend(char *text,
                                          size_t length,
                                          int32_t exponent,
                                          bool uppercase)
{
    char exponent_digits[12];
    const uint32_t magnitude = (uint32_t)((exponent < 0) ?
        -(int64_t)exponent : (int64_t)exponent);
    const size_t exponent_length = CommonFormat_UnsignedCreate(
        exponent_digits, magnitude, 10U, false);

    text[length++] = uppercase ? 'E' : 'e';
    text[length++] = (exponent < 0) ? '-' : '+';
    if (exponent_length < 2U) { text[length++] = '0'; }
    (void)memcpy(&text[length], exponent_digits, exponent_length);
    return length + exponent_length;
}

static size_t CommonFormat_GeneralCreate(char *text,
                                         double value,
                                         uint32_t precision,
                                         bool uppercase)
{
    const uint32_t bounded_precision = (precision == 0U) ? 1U :
        ((precision > COMMON_FORMAT_MAX_FLOAT_PRECISION) ?
            COMMON_FORMAT_MAX_FLOAT_PRECISION : precision);
    double normalized;
    double rounded_normalized;
    const uint64_t scale = CommonFormat_Power10Get(bounded_precision - 1U);
    int32_t exponent;
    int32_t fixed_precision;
    size_t length;

    SILVERSTAR_ASSERT_OBJECT(text, char, SILVERSTAR_ASSERT_MODULE_COMMON);
    if (value == 0.0) { text[0] = '0'; return 1U; }
    exponent = CommonFormat_DecimalExponentGet(value, &normalized);
    rounded_normalized = floor((normalized * (double)scale) + 0.5) /
        (double)scale;
    if (rounded_normalized >= 10.0)
    {
        rounded_normalized = 1.0;
        exponent++;
    }
    if ((exponent >= -4) && (exponent < (int32_t)bounded_precision))
    {
        fixed_precision = (int32_t)bounded_precision - exponent - 1;
        if (fixed_precision < 0) { fixed_precision = 0; }
        return CommonFormat_FixedCreate(
            text, value, (uint32_t)fixed_precision, true);
    }
    length = CommonFormat_FixedCreate(
        text, rounded_normalized, bounded_precision - 1U, true);
    return CommonFormat_ExponentAppend(text, length, exponent, uppercase);
}

static size_t CommonFormat_FloatCreate(char *text,
                                       double value,
                                       uint32_t precision,
                                       char conversion)
{
    const bool uppercase = ((conversion == 'F') || (conversion == 'G'));
    const bool negative = signbit(value) != 0;
    size_t length = 0U;

    SILVERSTAR_ASSERT_OBJECT(text, char, SILVERSTAR_ASSERT_MODULE_COMMON);
    if (negative) { text[length++] = '-'; value = -value; }
    if (isnan(value))
    {
        (void)memcpy(&text[length], uppercase ? "NAN" : "nan", 3U);
        return length + 3U;
    }
    if (isinf(value))
    {
        (void)memcpy(&text[length], uppercase ? "INF" : "inf", 3U);
        return length + 3U;
    }
    if ((conversion == 'g') || (conversion == 'G'))
    {
        length += CommonFormat_GeneralCreate(
            &text[length], value, precision, uppercase);
    }
    else
    {
        length += CommonFormat_FixedCreate(
            &text[length], value, precision, false);
    }
    return length;
}

static uint64_t CommonFormat_UnsignedArgumentGet(va_list *arguments,
                                                  CommonFormatLength length)
{
    if (length == COMMON_FORMAT_LENGTH_LONG_LONG)
    { return va_arg(*arguments, unsigned long long); }
    if (length == COMMON_FORMAT_LENGTH_LONG)
    { return va_arg(*arguments, unsigned long); }
    if (length == COMMON_FORMAT_LENGTH_SIZE)
    { return va_arg(*arguments, size_t); }
    return va_arg(*arguments, unsigned int);
}

static int64_t CommonFormat_SignedArgumentGet(va_list *arguments,
                                               CommonFormatLength length)
{
    if (length == COMMON_FORMAT_LENGTH_LONG_LONG)
    { return va_arg(*arguments, long long); }
    if (length == COMMON_FORMAT_LENGTH_LONG)
    { return va_arg(*arguments, long); }
    if (length == COMMON_FORMAT_LENGTH_SIZE)
    { return (int64_t)va_arg(*arguments, ptrdiff_t); }
    return va_arg(*arguments, int);
}

static void CommonFormat_SpecReset(CommonFormatSpec *spec)
{
    (void)memset(spec, 0, sizeof(*spec));
    spec->precision = -1;
    spec->length = COMMON_FORMAT_LENGTH_DEFAULT;
}

static uint8_t CommonFormat_FlagConsume(CommonFormatParser *parser,
                                        CommonFormatSpec *spec)
{
    const char current = CommonFormat_ParserCurrent(parser);

    if (current == '-') { spec->left_aligned = true; }
    else if (current == '0') { spec->zero_padded = true; }
    else if (current == '+') { spec->positive_sign = true; }
    else if (current == ' ') { spec->space_sign = true; }
    else if (current == '#') { spec->alternate_form = true; }
    else { return 0U; }
    CommonFormat_ParserAdvance(parser);
    return 1U;
}

static void CommonFormat_FlagsParse(CommonFormatParser *parser,
                                    CommonFormatSpec *spec)
{
    uint32_t index;

    for (index = 0U; index < COMMON_FORMAT_MAX_FLAG_CHARACTERS; index++)
    {
        if (CommonFormat_FlagConsume(parser, spec) == 0U) { break; }
    }
    SILVERSTAR_ASSERT(CommonFormat_FlagConsume(parser, spec) == 0U,
                      SILVERSTAR_ASSERT_MODULE_COMMON,
                      SILVERSTAR_ASSERT_REASON_LENGTH_RANGE);
}

static size_t CommonFormat_UnsignedDecimalParse(CommonFormatParser *parser,
                                                 uint32_t max_digits)
{
    size_t value = 0U;
    uint32_t index;
    char current;

    for (index = 0U; index < max_digits; index++)
    {
        current = CommonFormat_ParserCurrent(parser);
        if ((current < '0') || (current > '9')) { break; }
        value = (value * 10U) + (size_t)(current - '0');
        CommonFormat_ParserAdvance(parser);
    }
    current = CommonFormat_ParserCurrent(parser);
    SILVERSTAR_ASSERT((current < '0') || (current > '9'),
                      SILVERSTAR_ASSERT_MODULE_COMMON,
                      SILVERSTAR_ASSERT_REASON_LENGTH_RANGE);
    return value;
}

static void CommonFormat_WidthParse(CommonFormatParser *parser,
                                    CommonFormatSpec *spec)
{
    spec->width = CommonFormat_UnsignedDecimalParse(
        parser, COMMON_FORMAT_MAX_WIDTH_DIGITS);
    SILVERSTAR_ASSERT(spec->width <= COMMON_FORMAT_MAX_FIELD_WIDTH,
                      SILVERSTAR_ASSERT_MODULE_COMMON,
                      SILVERSTAR_ASSERT_REASON_LENGTH_RANGE);
}

static void CommonFormat_PrecisionParse(CommonFormatParser *parser,
                                        CommonFormatSpec *spec)
{
    size_t precision;

    if (CommonFormat_ParserCurrent(parser) != '.') { return; }
    CommonFormat_ParserAdvance(parser);
    precision = CommonFormat_UnsignedDecimalParse(
        parser, COMMON_FORMAT_MAX_PRECISION_DIGITS);
    SILVERSTAR_ASSERT(precision <= COMMON_FORMAT_MAX_PRECISION,
                      SILVERSTAR_ASSERT_MODULE_COMMON,
                      SILVERSTAR_ASSERT_REASON_LENGTH_RANGE);
    spec->precision = (int32_t)precision;
}

static void CommonFormat_LengthParse(CommonFormatParser *parser,
                                     CommonFormatSpec *spec)
{
    if (CommonFormat_ParserCurrent(parser) == 'l')
    {
        spec->length = COMMON_FORMAT_LENGTH_LONG;
        CommonFormat_ParserAdvance(parser);
        if (CommonFormat_ParserCurrent(parser) == 'l')
        {
            spec->length = COMMON_FORMAT_LENGTH_LONG_LONG;
            CommonFormat_ParserAdvance(parser);
        }
    }
    else if (CommonFormat_ParserCurrent(parser) == 'z')
    {
        spec->length = COMMON_FORMAT_LENGTH_SIZE;
        CommonFormat_ParserAdvance(parser);
    }
}

static uint8_t CommonFormat_SpecParse(CommonFormatParser *parser,
                                      CommonFormatSpec *spec)
{
    SILVERSTAR_ASSERT((parser != NULL) && (spec != NULL),
                      SILVERSTAR_ASSERT_MODULE_COMMON,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    CommonFormat_SpecReset(spec);
    CommonFormat_FlagsParse(parser, spec);
    CommonFormat_WidthParse(parser, spec);
    CommonFormat_PrecisionParse(parser, spec);
    CommonFormat_LengthParse(parser, spec);
    spec->conversion = CommonFormat_ParserCurrent(parser);
    if (spec->conversion == '\0') { return 0U; }
    CommonFormat_ParserAdvance(parser);
    return 1U;
}

static void CommonFormat_SignedPut(CommonFormatBuffer *buffer,
                                   const CommonFormatSpec *spec,
                                   va_list *arguments)
{
    char digits[COMMON_FORMAT_MAX_INTEGER_DIGITS];
    const int64_t signed_value = CommonFormat_SignedArgumentGet(
        arguments, spec->length);
    uint64_t magnitude;
    char sign = '\0';
    size_t digit_count;

    SILVERSTAR_ASSERT_OBJECT(buffer, CommonFormatBuffer,
                             SILVERSTAR_ASSERT_MODULE_COMMON);
    if (signed_value < 0)
    {
        sign = '-';
        magnitude = (uint64_t)(-(signed_value + 1)) + 1U;
    }
    else
    {
        magnitude = (uint64_t)signed_value;
        if (spec->positive_sign) { sign = '+'; }
        else if (spec->space_sign) { sign = ' '; }
    }
    digit_count = CommonFormat_UnsignedCreate(digits, magnitude, 10U, false);
    if ((spec->precision == 0) && (magnitude == 0U)) { digit_count = 0U; }
    CommonFormat_NumberPut(buffer, digits, digit_count, sign, "", 0U, spec);
}

static void CommonFormat_UnsignedPut(CommonFormatBuffer *buffer,
                                     const CommonFormatSpec *spec,
                                     va_list *arguments)
{
    char digits[COMMON_FORMAT_MAX_INTEGER_DIGITS];
    char prefix[2];
    const uint32_t radix = (spec->conversion == 'u') ? 10U : 16U;
    const uint64_t value = CommonFormat_UnsignedArgumentGet(
        arguments, spec->length);
    size_t digit_count = CommonFormat_UnsignedCreate(
        digits, value, radix, spec->conversion == 'X');
    size_t prefix_length = 0U;

    SILVERSTAR_ASSERT_OBJECT(buffer, CommonFormatBuffer,
                             SILVERSTAR_ASSERT_MODULE_COMMON);
    if ((spec->precision == 0) && (value == 0U)) { digit_count = 0U; }
    if (spec->alternate_form && (radix == 16U) && (value != 0U))
    {
        prefix[0] = '0';
        prefix[1] = (spec->conversion == 'X') ? 'X' : 'x';
        prefix_length = 2U;
    }
    CommonFormat_NumberPut(
        buffer, digits, digit_count, '\0', prefix, prefix_length, spec);
}

static size_t CommonFormat_StringLengthGet(const char *text)
{
    size_t length;

    for (length = 0U; length < COMMON_FORMAT_MAX_TEXT_LENGTH; length++)
    {
        if (text[length] == '\0') { return length; }
    }
    SILVERSTAR_ASSERT(length < COMMON_FORMAT_MAX_TEXT_LENGTH,
                      SILVERSTAR_ASSERT_MODULE_COMMON,
                      SILVERSTAR_ASSERT_REASON_LENGTH_RANGE);
    return 0U;
}

static void CommonFormat_StringPut(CommonFormatBuffer *buffer,
                                   const CommonFormatSpec *spec,
                                   va_list *arguments)
{
    const char *value = va_arg(*arguments, const char *);
    size_t value_length;

    if (value == NULL) { value = "(null)"; }
    value_length = CommonFormat_StringLengthGet(value);
    if ((spec->precision >= 0) &&
        ((size_t)spec->precision < value_length))
    {
        value_length = (size_t)spec->precision;
    }
    CommonFormat_FieldPut(buffer, value, value_length, spec, ' ');
}

static void CommonFormat_FloatPut(CommonFormatBuffer *buffer,
                                  const CommonFormatSpec *spec,
                                  va_list *arguments)
{
    char field[COMMON_FORMAT_FIELD_CAPACITY];
    const uint32_t precision = (spec->precision < 0) ? 6U :
        (uint32_t)spec->precision;
    size_t field_length = CommonFormat_FloatCreate(
        field, va_arg(*arguments, double), precision, spec->conversion);

    SILVERSTAR_ASSERT_OBJECT(buffer, CommonFormatBuffer,
                             SILVERSTAR_ASSERT_MODULE_COMMON);
    SILVERSTAR_ASSERT(field_length < COMMON_FORMAT_FIELD_CAPACITY,
                      SILVERSTAR_ASSERT_MODULE_COMMON,
                      SILVERSTAR_ASSERT_REASON_BUFFER_CAPACITY);
    if ((field_length != 0U) && (field[0] != '-') &&
        (spec->positive_sign || spec->space_sign))
    {
        const char sign = spec->positive_sign ? '+' : ' ';

        (void)memmove(&field[1], &field[0], field_length);
        field[0] = sign;
        field_length++;
    }
    CommonFormat_FieldPut(buffer, field, field_length, spec,
                          spec->zero_padded ? '0' : ' ');
}

static void CommonFormat_PointerPut(CommonFormatBuffer *buffer,
                                    const CommonFormatSpec *spec,
                                    va_list *arguments)
{
    char digits[2U * sizeof(uintptr_t)];
    const uintptr_t value = (uintptr_t)va_arg(*arguments, void *);
    const size_t digit_count = CommonFormat_UnsignedCreate(
        digits, (uint64_t)value, 16U, false);

    CommonFormat_NumberPut(
        buffer, digits, digit_count, '\0', "0x", 2U, spec);
}

static void CommonFormat_SpecRender(CommonFormatBuffer *buffer,
                                    const CommonFormatSpec *spec,
                                    va_list *arguments)
{
    SILVERSTAR_ASSERT_OBJECT(buffer, CommonFormatBuffer,
                             SILVERSTAR_ASSERT_MODULE_COMMON);
    if ((spec->conversion == 'd') || (spec->conversion == 'i'))
    { CommonFormat_SignedPut(buffer, spec, arguments); }
    else if ((spec->conversion == 'u') || (spec->conversion == 'x') ||
             (spec->conversion == 'X'))
    { CommonFormat_UnsignedPut(buffer, spec, arguments); }
    else if (spec->conversion == 's')
    { CommonFormat_StringPut(buffer, spec, arguments); }
    else if (spec->conversion == 'c')
    {
        const char value = (char)va_arg(*arguments, int);
        CommonFormat_FieldPut(buffer, &value, 1U, spec, ' ');
    }
    else if ((spec->conversion == 'f') || (spec->conversion == 'F') ||
             (spec->conversion == 'g') || (spec->conversion == 'G'))
    { CommonFormat_FloatPut(buffer, spec, arguments); }
    else if (spec->conversion == 'p')
    { CommonFormat_PointerPut(buffer, spec, arguments); }
    else
    {
        CommonFormat_CharacterPut(buffer, '%');
        CommonFormat_CharacterPut(buffer, spec->conversion);
    }
}

static void CommonFormat_Terminate(CommonFormatBuffer *buffer)
{
    if ((buffer->text != NULL) && (buffer->capacity != 0U))
    {
        const size_t terminator = (buffer->length < buffer->capacity) ?
            buffer->length : (buffer->capacity - 1U);
        buffer->text[terminator] = '\0';
    }
}

static int32_t CommonFormat_InternalPrint(CommonFormatBuffer *buffer,
                                          const char *format,
                                          va_list *arguments)
{
    CommonFormatParser parser = { format, COMMON_FORMAT_MAX_FORMAT_LENGTH };
    CommonFormatSpec spec;
    uint32_t format_index;
    uint8_t terminated = 0U;

    SILVERSTAR_ASSERT((buffer != NULL) && (format != NULL) &&
                      (arguments != NULL),
                      SILVERSTAR_ASSERT_MODULE_COMMON,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(buffer->length == 0U,
                      SILVERSTAR_ASSERT_MODULE_COMMON,
                      SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    for (format_index = 0U;
         format_index < COMMON_FORMAT_MAX_FORMAT_LENGTH;
         format_index++)
    {
        const char current = CommonFormat_ParserCurrent(&parser);

        if (current == '\0')
        {
            terminated = (parser.remaining != 0U) ? 1U : 0U;
            break;
        }
        CommonFormat_ParserAdvance(&parser);
        if (current != '%')
        {
            CommonFormat_CharacterPut(buffer, current);
        }
        else if (CommonFormat_ParserCurrent(&parser) == '%')
        {
            CommonFormat_CharacterPut(buffer, '%');
            CommonFormat_ParserAdvance(&parser);
        }
        else if (CommonFormat_SpecParse(&parser, &spec) == 0U)
        {
            CommonFormat_CharacterPut(buffer, '%');
            terminated = 1U;
            break;
        }
        else { CommonFormat_SpecRender(buffer, &spec, arguments); }
    }
    SILVERSTAR_ASSERT(terminated != 0U, SILVERSTAR_ASSERT_MODULE_COMMON,
                      SILVERSTAR_ASSERT_REASON_LOOP_BOUND);
    CommonFormat_Terminate(buffer);
    return (buffer->length > (size_t)INT32_MAX) ?
        INT32_MAX : (int32_t)buffer->length;
}

int32_t CommonFormat_VPrint(char *text,
                            size_t capacity,
                            const char *format,
                            va_list arguments)
{
    CommonFormatBuffer buffer = { text, capacity, 0U };
    va_list argument_copy;
    int32_t result;

    if ((format == NULL) || ((capacity != 0U) && (text == NULL)))
    {
        if ((text != NULL) && (capacity != 0U)) { text[0] = '\0'; }
        return -1;
    }
    va_copy(argument_copy, arguments);
    result = CommonFormat_InternalPrint(&buffer, format, &argument_copy);
    va_end(argument_copy);
    return result;
}

int32_t CommonFormat_Print(char *text,
                           size_t capacity,
                           const char *format,
                           ...)
{
    va_list arguments;
    int32_t result;

    va_start(arguments, format);
    result = CommonFormat_VPrint(text, capacity, format, arguments);
    va_end(arguments);
    return result;
}
