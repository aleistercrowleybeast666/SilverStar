uint8_t Estimator_GetLatestSnapshot(EstimatorOutputSnapshot *snapshot)
{
    EstimatorOutputSnapshot published;
    uint32_t primask;

    if (snapshot == NULL)
    {
        return 0U;
    }
    primask = EstimatorTask_IrqLock();
    published = s_published_snapshot;
    EstimatorTask_IrqUnlock(primask);
    *snapshot = published;
    return published.initialized;
}
