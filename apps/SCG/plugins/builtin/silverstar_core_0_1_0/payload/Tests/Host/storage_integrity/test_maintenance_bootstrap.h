/* Host-only fault injection. Actual LoggerBus/LoggerTask/codec/FatFs/diskio
 * execute; only scheduler, readiness providers and card completion are models.
 * setjmp/longjmp terminates the Host scheduler and is never target firmware. */
#ifndef __TEST_MAINTENANCE_BOOTSTRAP_H
#define __TEST_MAINTENANCE_BOOTSTRAP_H

static uint32_t s_bootstrap_enter_count;
static uint32_t s_bootstrap_close_faults;
static uint8_t s_bootstrap_deadline;
static uint8_t s_bootstrap_in_hook;

static uint8_t Fixture_BootstrapMaintenanceCase(const char *mode)
{
    static const char *const modes[] = {
        "maintenance-bootstrap", "maintenance-calibration-failed",
        "maintenance-sensor-unready", "maintenance-early-bootstrap",
        "maintenance-repeat-enter", "maintenance-write-timeout",
        "maintenance-close-fault", "maintenance-final-status-fault"
    };
    for (uint8_t index = 0U; index < sizeof(modes) / sizeof(modes[0]); index++)
    { if (strcmp(mode, modes[index]) == 0) { return (uint8_t)(index + 1U); } }
    return 0U;
}

static void Fixture_BootstrapRequire(uint8_t condition, const char *detail)
{
    if (!condition)
    {
        fprintf(stderr, "BOOTSTRAP_MAINTENANCE_FAIL %s\n", detail);
        s_failures++;
        longjmp(s_exit, 2);
    }
}

/* Explicit f_close-result fault only. All ordinary closes execute real FatFs.
 * The final-status case instead injects card-start failure after writer close. */
FRESULT __real_f_close(FIL *file);
FRESULT __wrap_f_close(FIL *file)
{
    FRESULT result;
    if (s_fixture_maintenance == SystemMaintenanceState_Draining &&
        s_bootstrap_maintenance_case == 7U && s_bootstrap_close_faults == 0U)
    { s_bootstrap_close_faults++; return FR_DISK_ERR; }
    result = __real_f_close(file);
    if (s_fixture_maintenance == SystemMaintenanceState_Draining &&
        s_bootstrap_maintenance_case == 8U && result == FR_OK)
    { s_start_failure = 1U; }
    return result;
}

static void Fixture_BootstrapMaintenanceDelay(void)
{
    char reply[512];
    uint32_t before;
    if (s_bootstrap_in_hook) { return; }
    s_bootstrap_in_hook = 1U;
    if (++s_maintenance_steps >= 512U)
    { s_bootstrap_deadline = 1U; longjmp(s_exit, 1); }
    if (s_fixture_maintenance == SystemMaintenanceState_Ready ||
        s_fixture_maintenance == SystemMaintenanceState_Failed) { longjmp(s_exit, 1); }
    if (s_fixture_maintenance == SystemMaintenanceState_Off &&
        (s_bootstrap_maintenance_case <= 5U ||
         LoggerBus_StartupStateGet() == LOGGER_STREAMING_READY))
    {
        before = s_dma_transactions;
        Fixture_BootstrapRequire(SystemLogFile_ExecuteLine("LOGFILE ENTER", reply,
            sizeof(reply)) == SYSTEM_CONSOLE_EXECUTE_OK && strstr(reply, "accepted=1") != NULL,
            "ENTER must reserve maintenance");
        Fixture_BootstrapRequire(s_dma_transactions == before, "Serial ENTER must perform no disk I/O");
        s_bootstrap_enter_count++;
        if (s_bootstrap_maintenance_case == 5U)
        {
            for (uint8_t repeat = 0U; repeat < 3U; repeat++)
            {
                Fixture_BootstrapRequire(SystemLogFile_ExecuteLine("LOGFILE ENTER", reply,
                    sizeof(reply)) == SYSTEM_CONSOLE_EXECUTE_OK && strstr(reply, "accepted=1") != NULL,
                    "repeated ENTER must remain accepted");
                s_bootstrap_enter_count++;
            }
        }
        Fixture_BootstrapRequire(s_fixture_maintenance == SystemMaintenanceState_Draining,
            "ACK must not imply maintenance READY");
        before = s_dma_transactions;
        Fixture_BootstrapRequire(SystemLogFileStorage_Check(1U, 0U) != SystemLogFileResult_Ok,
            "reads must remain closed while draining");
        Fixture_BootstrapRequire(s_dma_transactions == before, "denied read must perform no disk I/O");
        if (s_bootstrap_maintenance_case == 6U)
        {
            for (uint32_t item = 0U; item < 32U; item++)
            {
                Fixture_BootstrapRequire(LoggerBus_EventPush(PlatformTime_Us(),
                    FLIGHT_LOG_EVENT_BOOT, item, 0U) == LOGGER_BUS_RESULT_OK,
                    "pre-close admitted records must fit the existing queue");
            }
            s_timeout = 1U;
        }
    }
    s_bootstrap_in_hook = 0U;
}

static int Fixture_MaintenanceLogSave(const char *output)
{
    uint32_t mission;
    char name[64];
    uint8_t data[512];
    UINT count;
    FILE *saved;
    CHECK(SystemStorage_MissionIdGet(&mission) == SYSTEM_DEVICE_OK);
    CHECK(snprintf(name, sizeof(name), "0:/missions/%06lu/flight.sslog", (unsigned long)mission) > 0);
    CHECK(f_open(&s_file, name, FA_READ) == FR_OK);
    saved = fopen(output, "wb");
    CHECK(saved != NULL);
    for (uint32_t block = 0U; block < 128U; block++)
    {
        CHECK(f_read(&s_file, data, sizeof(data), &count) == FR_OK);
        CHECK(fwrite(data, 1U, count, saved) == count);
        if (count == 0U) { break; }
        CHECK(block + 1U < 128U);
    }
    CHECK(fclose(saved) == 0 && f_close(&s_file) == FR_OK);
    return 1;
}

static int Test_BootstrapMaintenance(const char *output, const char *mode)
{
    LoggerTaskDiagnostics diagnostics;
    LoggerBusDiagnostics bus;
    SystemStorageHealth health;
    uint32_t before;
    char reply[512];
    s_bootstrap_maintenance_case = Fixture_BootstrapMaintenanceCase(mode);
    s_fixture_calibration_ready = (uint8_t)(s_bootstrap_maintenance_case != 2U &&
        s_bootstrap_maintenance_case != 4U && s_bootstrap_maintenance_case != 5U);
    s_fixture_imu_unavailable = (uint8_t)(s_bootstrap_maintenance_case == 3U);
    s_startup.completed = (uint8_t)(s_bootstrap_maintenance_case != 1U && s_bootstrap_maintenance_case != 4U);
    s_startup.passed = (uint8_t)!s_fixture_imu_unavailable;
    CHECK(LoggerBus_Init() == LOGGER_BUS_RESULT_OK);
    CHECK(LoggerBus_EventPush(PlatformTime_Us(), FLIGHT_LOG_EVENT_BOOT, 0U, 0U) == LOGGER_BUS_RESULT_OK);
    if (setjmp(s_exit) == 0) { AppTask_Logger(NULL); }
    CHECK(LoggerTask_DiagnosticsGet(&diagnostics) == SYSTEM_DEVICE_OK);
    CHECK(LoggerBus_DiagnosticsGet(&bus) == LOGGER_BUS_RESULT_OK);
    CHECK(SystemStorage_HealthGet(&health) == SYSTEM_DEVICE_OK);
    printf("BOOTSTRAP_MAINTENANCE mode=%s state=%u startup=%u snapshot_ready=%u writer_open=%u final=%u fault=%u deadline=%u steps=%lu\n",
        mode, s_fixture_maintenance, bus.startup_state, diagnostics.snapshot_ready,
        health.file_open, LoggerBus_FinalizationStateGet(), diagnostics.io_fault,
        s_bootstrap_deadline, (unsigned long)s_maintenance_steps);
    CHECK(s_failures == 0U && s_bootstrap_deadline == 0U && s_bootstrap_enter_count != 0U);
    if (s_bootstrap_maintenance_case >= 6U)
    {
        CHECK(s_fixture_maintenance == SystemMaintenanceState_Failed);
        CHECK(diagnostics.io_fault != 0U || diagnostics.final_status_write_failed != 0U);
        if (s_bootstrap_maintenance_case == 6U) { CHECK(diagnostics.append_failure_count != 0U); }
        if (s_bootstrap_maintenance_case == 7U) { CHECK(s_bootstrap_close_faults == 1U && diagnostics.close_failure_count != 0U); }
        if (s_bootstrap_maintenance_case == 8U) { CHECK(diagnostics.final_status_write_failed != 0U); }
        before = s_dma_transactions;
        CHECK(SystemLogFileStorage_Check(1U, 0U) != SystemLogFileResult_Ok);
        CHECK(s_dma_transactions == before);
        return 1;
    }
    CHECK(s_fixture_maintenance == SystemMaintenanceState_Ready);
    CHECK(health.file_open == 0U && diagnostics.io_fault == 0U && diagnostics.final_status_write_failed == 0U);
    CHECK(LoggerBus_FinalizationStateGet() == LOGGER_BUS_FINALIZATION_FINALIZED);
    CHECK(LoggerBus_Count() == 0U && bus.accepted_count == bus.dequeued_count);
    CHECK(bus.startup_state == LOGGER_BOOTSTRAP && diagnostics.streaming_ready_us == 0ULL);
    CHECK(diagnostics.snapshot_ready == 0U && diagnostics.discarded_bytes == 0U);
    CHECK(LoggerBus_EventPush(PlatformTime_Us(), FLIGHT_LOG_EVENT_BOOT, 0U, 0U) == LOGGER_BUS_RESULT_BAD_STATE);
    if (s_bootstrap_maintenance_case == 5U)
    {
        CHECK(s_bootstrap_enter_count == 4U);
        before = s_dma_transactions;
        CHECK(SystemLogFile_ExecuteLine("LOGFILE ENTER", reply, sizeof(reply)) == SYSTEM_CONSOLE_EXECUTE_OK);
        CHECK(s_fixture_maintenance == SystemMaintenanceState_Ready && s_dma_transactions == before);
    }
    CHECK(Fixture_MaintenanceLogSave(output) == 1);
    return 1;
}

#endif /* __TEST_MAINTENANCE_BOOTSTRAP_H */
