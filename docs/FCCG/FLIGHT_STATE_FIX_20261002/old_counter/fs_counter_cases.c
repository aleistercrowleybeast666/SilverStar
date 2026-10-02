static uint8_t s_estimator_available = 1U;
uint8_t Estimator_GetLatestSnapshot(EstimatorOutputSnapshot *snapshot)
{
    if ((snapshot == NULL) || (s_estimator_available == 0U)) { return 0U; }
    (void)memset(snapshot, 0, sizeof(*snapshot));
    snapshot->initialized = 1U;
    snapshot->q_nb[0] = 1.0f;
    snapshot->velocity_enu_mps[0] = -0.0981511548f;
    snapshot->velocity_enu_mps[1] = 0.0991782993f;
    snapshot->velocity_enu_mps[2] = 0.0932015106f;
    snapshot->position_enu_m[0] = -0.467806935f;
    snapshot->position_enu_m[1] = 0.483857244f;
    snapshot->position_enu_m[2] = 0.072262131f;
    return 1U;
}
