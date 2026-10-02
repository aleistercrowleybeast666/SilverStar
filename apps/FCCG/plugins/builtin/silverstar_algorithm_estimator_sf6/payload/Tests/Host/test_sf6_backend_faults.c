/* Host only: include the real owner to fault-inject private stored state.
 * No test setter, callback or recovery mechanism enters target firmware. */
#define main Test_NormalEntry
#include "test_sf6_backend.c"
#undef main
#include "../../Algorithm/Estimator/SF6/Src/navigation_sf6_backend.c"

int main(int argc, char **argv)
{
    const float q[4] = {1.0f, 0.0f, 0.0f, 0.0f};
    const float position[3] = {0.0f, 0.0f, 0.0f};
    EstimatorOutputSnapshot output = {0};
    if (argc != 2) { return 2; }
    HostPlatformMock_Reset();
    if (SystemTime_Init() != SYSTEM_DEVICE_OK) { return 2; }
    Test_GnssPrepare();
    if (SystemNavigationBackend_Initialize(q, &s_gnss, 10.0f, 1U, 80U, 1U) != SYSTEM_DEVICE_OK) { return 2; }
    if (strcmp(argv[1], "gnss_group_4") == 0 ||
        strcmp(argv[1], "gnss_group_32") == 0 || strcmp(argv[1], "gnss_group_255") == 0)
    {
        uint8_t group = strcmp(argv[1], "gnss_group_4") == 0 ? 4U :
            (strcmp(argv[1], "gnss_group_32") == 0 ? 32U : 255U);
        Backend_GnssGroupApply(&s_gnss, position, group, &output);
        return 3;
    }
    if (strcmp(argv[1], "q_nonfinite") == 0) { s_q_nb[0] = NAN; }
    else if (strcmp(argv[1], "q_nonunit") == 0) { s_q_nb[0] = 0.0f; }
    else if (strcmp(argv[1], "baro_flag") == 0) { s_baro_origin_valid = 2U; }
    else if (strcmp(argv[1], "baro_reference") == 0) { s_baro_origin = INFINITY; }
    else { return 2; }
    (void)SystemNavigationBackend_SnapshotGet(&output);
    return 3; /* Returning a snapshot of corrupt stored state is the defect. */
}
