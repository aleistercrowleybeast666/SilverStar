/* Host differential access to private kernels; never linked in firmware. */
#include NAV_PERF_SOURCE

void NavPerf_EskfReset(NavigationEskfWorkspace *work)
{
    Eskf_ResetJacobianBuild(work);
}

void NavPerf_EskfTransition(NavigationEskfWorkspace *work, float dt)
{
    Eskf_TransitionBuild(work, dt);
}

void NavPerf_EskfNoise(NavigationEskfWorkspace *work,
    const NavigationEskfConfig *config, float dt, float quality)
{
    Eskf_NoiseAdd(work, config, dt, quality);
}
