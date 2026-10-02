SystemDeviceResult SystemInertial_LatestGet(SystemInertialSample *sample)
{
    SystemImuSample device_sample;
    SystemDeviceResult result;

    if (sample == NULL)
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    if (s_initialized == 0U)
    {
        return SYSTEM_DEVICE_NOT_READY;
    }
    result = SystemImu_LatestSampleGet(&device_sample);
    if (result != SYSTEM_DEVICE_OK)
    {
        return result;
    }
    SystemInertial_DeviceSampleCopy(&device_sample, sample);
    return SYSTEM_DEVICE_OK;
}
