/* Host-only access to the actual private kernel, without redefining static. */
#include NAV_ESKF_TEST_SOURCE

void Test_EskfResetNumeric(const float correction[3], const float covariance[225],
    float jacobian[9], float transformed[225]);

void Test_EskfResetNumeric(const float correction[3], const float covariance[225],
    float jacobian[9], float transformed[225])
{
    static NavigationEskfWorkspace work;
    memset(&work, 0, sizeof(work));
    memcpy(work.correction + 6, correction, 3U * sizeof(float));
    memcpy(work.candidate_p, covariance, sizeof(work.candidate_p));
#if NAV_ESKF_TEST_RESET_REVISION == 2
    Eskf_ResetJacobianRevision2Build(&work);
#else
    Eskf_ResetJacobianBuild(&work);
#endif
    for (uint32_t i = 0U; i < 3U; i++)
    {
        for (uint32_t j = 0U; j < 3U; j++)
        { jacobian[i * 3U + j] = work.transition[6U + i][6U + j]; }
    }
    memcpy(transformed, work.candidate_p, sizeof(work.candidate_p));
}
