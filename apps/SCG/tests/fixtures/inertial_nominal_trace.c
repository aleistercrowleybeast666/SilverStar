#include <math.h>
#include <stdio.h>
#include "ins_mechanization.h"

int main(int argc, char **argv)
{
    InsMechanizationContext context;
    InsAlgorithmSample sample = {0};
    InsState state;
    const float q[4] = {1.0f, 0.0f, 0.0f, 0.0f};
    if (argc != 2) { return 1; }
    FILE *output = fopen(argv[1], "wb");
    if (output == NULL) { return 2; }
    InsMechanization_Init(&context, 9.78f);
    if (!InsMechanization_ResetNavigationWithAttitude(&context, q)) { return 3; }
    sample.valid_flags = INS_ALGORITHM_VALID_ACCEL | INS_ALGORITHM_VALID_GYRO;
    for (unsigned int i = 0U; i < 2001U; i++)
    {
        sample.timestamp_us = 1000000ULL + (uint64_t)i * 5000ULL;
        sample.gyro_b_radps[0] = (float)(i % 13U) * 0.003f;
        sample.gyro_b_radps[1] = (float)(i % 17U) * -0.002f;
        sample.accel_b_mps2[0] = (float)(i % 11U) * 0.13f;
        sample.accel_b_mps2[2] = 9.78f;
        if (InsMechanization_Update(&context, &sample, &state))
        { if (fwrite(&state, sizeof(state), 1U, output) != 1U) { return 4; } }
    }
    return fclose(output) != 0;
}
