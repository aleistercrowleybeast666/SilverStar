/* Isolated resource/encoding experiment. Not linked into target firmware.
 * The CPU-only state models reserved capacity, not completed source binding,
 * SHA/INFO generation, acquisition, interrupt ownership or MCU recovery. */
#include <stddef.h>
#include <stdint.h>

typedef struct {
    uint64_t sample_us;
    uint64_t receive_us;
    uint32_t sequence, epoch, uncertainty_us, flags;
    float physical[6];
    int32_t raw[6];
    float temperature;
} PendingSource;

typedef struct {
    uint32_t configuration, driver_hash, model_hash, epoch;
    uint32_t stride, intrinsic_crc, intrinsic_generation, uncertainty_us;
    uint16_t descriptor, physical;
    uint8_t instance, frame, clock, correction;
    int8_t axis_map[3];
    uint8_t flags;
} FrozenSource;

typedef struct {
    FrozenSource sources[2];
    double accel_bias[3], accel_matrix[9], gyro_bias[3];
    double mag_bias[3], mag_matrix[9], mag_reference;
    double R_GA[9];
    uint8_t intrinsic_digest[2][32];
    uint8_t boot_witness[16], binding_digest[32];
    uint32_t configuration, base_generation, snapshot_revision;
    uint8_t validity[8];
    double accel_norm_min, accel_norm_max, gyro_norm_max;
    double mag_norm_min, mag_norm_max, accel_variance, mag_variance, temperature_span;
    uint32_t maximum_skew_us, maximum_uncertainty_us, source_timeout_us, face_timeout_us;
} FrozenMetadata;

typedef union {
    FrozenMetadata fields;
    uint8_t reserved[640];
} FrozenCapacity;

typedef struct {
    uint8_t sid[16], request_digest[32];
    uint64_t face_start, source_last[2], lease_last;
    uint32_t rid, face_rid, next_pair, train_last_pair;
    uint32_t train_last_sequence[2], holdout_first_sequence[2];
    uint32_t train_count, holdout_count;
    uint16_t attempt;
    uint8_t mode, stage, face, phase;
    uint8_t command_mailbox[64];
} Transaction;

typedef union {
    Transaction fields;
    uint8_t reserved[256];
} TransactionCapacity;

typedef struct {
    uint8_t parts[2][154];
    uint32_t pair_id;
    uint8_t committed_parts;
} PairSlot;

typedef struct {
    PairSlot pairs[2];
    PendingSource pending[2];
    FrozenCapacity frozen;
    TransactionCapacity transaction;
    uint8_t sha_workspace[128];
    uint8_t encoder_cursor[32];
    /* Includes proposed global lease gate, native continuity counters, queue
     * publication/consumer ownership and fault flags. Implementation unproven. */
    uint32_t owner_queue_and_fault_state[24];
} CaptureState;

_Static_assert(sizeof(FrozenMetadata) <= 640U, "Frozen metadata exceeds reservation");
_Static_assert(sizeof(Transaction) <= 256U, "Transaction exceeds reservation");
_Static_assert(sizeof(CaptureState) <= 2048U, "Capture CCM cap exceeded");

static CaptureState s_capture __attribute__((used, section(".capture_ccm"), aligned(8)));
const uint32_t LayoutSummary[] __attribute__((section(".layout"))) = {
    sizeof(CaptureState), sizeof(PairSlot), sizeof(PendingSource),
    sizeof(FrozenMetadata), sizeof(FrozenCapacity), sizeof(Transaction),
    sizeof(TransactionCapacity), offsetof(CaptureState, sha_workspace),
    _Alignof(CaptureState), offsetof(CaptureState, pending),
    offsetof(CaptureState, frozen), offsetof(CaptureState, transaction),
    offsetof(CaptureState, encoder_cursor), offsetof(CaptureState, owner_queue_and_fault_state)
};

typedef enum {
    StreamEncodeResult_Ok,
    StreamEncodeResult_Invalid,
    StreamEncodeResult_Capacity
} StreamEncodeResult;

static char Stream_Hex(uint8_t value)
{
    return "0123456789ABCDEF"[value & 15U];
}

static uint32_t Stream_Crc(const uint8_t *data)
{
    uint32_t crc = UINT32_MAX;
    uint16_t index;
    uint8_t bit;
    for (index = 0U; index < 154U; index++) {
        crc ^= data[index];
        for (bit = 0U; bit < 8U; bit++) {
            crc = (crc >> 1) ^ ((crc & 1U) != 0U ? UINT32_C(0xEDB88320) : 0U);
        }
    }
    return ~crc;
}

static uint16_t Stream_Text(char *output, uint16_t offset,
                            const char *text, uint16_t size)
{
    uint16_t index;
    for (index = 0U; index < size; index++) { output[offset++] = text[index]; }
    return offset;
}

static uint16_t Stream_Bytes(char *output, uint16_t offset,
                             const uint8_t *input, uint16_t size)
{
    uint16_t index;
    for (index = 0U; index < size; index++) {
        output[offset++] = Stream_Hex((uint8_t)(input[index] >> 4));
        output[offset++] = Stream_Hex(input[index]);
    }
    return offset;
}

static uint16_t Stream_Number(char *output, uint16_t offset, uint32_t value)
{
    uint32_t divisor = UINT32_C(1000000000);
    uint8_t index, started = 0U;
    for (index = 0U; index < 10U; index++) {
        uint32_t digit = value / divisor;
        if ((digit != 0U) || (started != 0U) || (divisor == 1U)) {
            output[offset++] = (char)('0' + digit);
            started = 1U;
        }
        value %= divisor;
        divisor = (divisor > 1U) ? divisor / 10U : 1U;
    }
    return offset;
}

/* Caller owns an existing SerialTask scratch buffer. No retained pointer.
 * 439 includes the optional local NUL; max wire line is 438 including CRLF.
 * Production integration must use lowercase sid/binding convention: body hex
 * is uppercase, identity hex is lowercase. */
StreamEncodeResult Stream_EncodeEvent(char *output, uint16_t capacity,
    uint16_t *length, const uint8_t *body, uint8_t mag, uint32_t pair_id,
    const uint8_t *sid, const uint8_t *binding)
{
    uint16_t n = 0U, index;
    uint32_t crc;
    if ((output == NULL) || (length == NULL) || (body == NULL) ||
        (sid == NULL) || (binding == NULL) || (mag > 1U) || (pair_id == 0U)) {
        return StreamEncodeResult_Invalid;
    }
    *length = 0U;
    if (capacity < 439U) { return StreamEncodeResult_Capacity; }
    n = Stream_Text(output, n, "EVENT INSTALL ", 14U);
    n = Stream_Text(output, n, mag != 0U ? "MAG" : "IMU", 3U);
    n = Stream_Text(output, n, " sid=", 5U);
    n = Stream_Bytes(output, n, sid, 16U);
    for (index = 22U; index < 54U; index++) {
        if ((output[index] >= 'A') && (output[index] <= 'F')) { output[index] += 32; }
    }
    n = Stream_Text(output, n, " pair=", 6U);
    n = Stream_Number(output, n, pair_id);
    n = Stream_Text(output, n, " ctx=B-", 7U);
    index = n;
    n = Stream_Bytes(output, n, binding, 15U);
    for (; index < n; index++) {
        if ((output[index] >= 'A') && (output[index] <= 'F')) { output[index] += 32; }
    }
    n = Stream_Text(output, n, " data=", 6U);
    n = Stream_Bytes(output, n, body, 154U);
    n = Stream_Text(output, n, " crc32=", 7U);
    crc = Stream_Crc(body);
    for (index = 0U; index < 8U; index++) {
        output[n++] = Stream_Hex((uint8_t)(crc >> (28U - 4U * index)));
    }
    output[n++] = '\r'; output[n++] = '\n'; output[n] = '\0';
    *length = n;
    return StreamEncodeResult_Ok;
}

/* Keeps the entire state and encoder reachable in a standalone ARM ELF.
 * This is not startup code, and the ELF must never be flashed. */
StreamEncodeResult Experiment_Entry(char *scratch, uint16_t *length)
{
    s_capture.owner_queue_and_fault_state[0] = 1U;
    return Stream_EncodeEvent(scratch, 439U, length,
        s_capture.pairs[0].parts[0], 0U, UINT32_MAX,
        s_capture.transaction.fields.sid, s_capture.frozen.fields.binding_digest);
}

#ifdef EXPERIMENT_HOST
#include <assert.h>
#include <stdio.h>
#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#endif
int main(void)
{
    char line[441];
    uint8_t body[154], sid[16], binding[15];
    uint16_t index, length;
#ifdef _WIN32
    assert(_setmode(_fileno(stdout), _O_BINARY) != -1);
#endif
    for (index = 0U; index < 154U; index++) { body[index] = (uint8_t)index; }
    for (index = 0U; index < 16U; index++) { sid[index] = 0xFFU; }
    for (index = 0U; index < 15U; index++) { binding[index] = 0xABU; }
    line[0] = 'Q'; line[439] = 'X'; line[440] = 'Y';
    assert(Stream_EncodeEvent(line, 438U, &length, body, 0U, 1U, sid, binding)
           == StreamEncodeResult_Capacity && length == 0U && line[0] == 'Q');
    assert(Stream_EncodeEvent(NULL, 439U, &length, body, 0U, 1U, sid, binding)
           == StreamEncodeResult_Invalid);
    assert(Stream_EncodeEvent(line, 439U, &length, body, 2U, 1U, sid, binding)
           == StreamEncodeResult_Invalid);
    assert(Stream_EncodeEvent(line, 439U, &length, body, 0U, 0U, sid, binding)
           == StreamEncodeResult_Invalid);
    assert(Stream_EncodeEvent(line, 439U, &length, body, 0U, UINT32_MAX, sid, binding)
           == StreamEncodeResult_Ok);
    assert(length == 438U && line[438] == '\0' && line[439] == 'X' && line[440] == 'Y');
    assert(fwrite(line, 1U, length, stdout) == length);
    return 0;
}
#endif
