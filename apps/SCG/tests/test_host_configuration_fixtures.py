"""Host substitutions retain production selection and UART rejection guards."""
import os
from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.fixture(scope="module")
def project(tmp_path_factory, workspace_root):
    configured = os.environ.get("SILVERSTAR_HOST_FIXTURE_PROJECT")
    if configured:
        return Path(configured)
    from silverstar_fccg.app.service import FccgService
    service = FccgService(workspace_root)
    destination = tmp_path_factory.mktemp("host_configuration") / "project"
    service.Project_Save(service.ReferenceProject_Create("HostConfiguration"),
                         destination, confirm_dangerous=True)
    return destination


def _compiler(project):
    compiler = shutil.which("gcc")
    assert compiler, "Host GCC is required"
    args = [compiler, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
            "-pedantic", "-fanalyzer", "-include",
            str(project / "Generated/Inc/project_flight_config.h")]
    for path in project.rglob("Inc"):
        if "build" not in path.relative_to(project).parts:
            args += ["-I", str(path)]
    return args


@pytest.mark.parametrize("include_fixture", [False, True])
def test_host_fixture_cannot_bypass_production_selection(project, tmp_path, include_fixture):
    source = tmp_path / "selection.c"
    source.write_text("int main(void) { return 0; }\n", encoding="utf-8")
    args = _compiler(project) + ["-DSYSTEM_USER_MAGNETOMETER_ENABLE=1U"]
    if include_fixture:
        args += ["-include", str(project / "Tests/Host/Fixtures/magnetic_provider_contract.h")]
    result = subprocess.run(args + ["-fsyntax-only", str(source)],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode != 0
    assert "Enable override conflicts with explicit magnetic device selection" in result.stderr


def test_generated_resources_keep_real_uart_guard_with_host_state(project, tmp_path):
    import json
    profile = json.loads((project / "Tools/maintenance_uart.json").read_text())
    handle, peripheral, baud = profile["handle"], profile["peripheral"], profile["baudrate"]
    fixture = project / "Tests/Host/Fixtures/MaintenanceUart"
    source = tmp_path / "uart_guard.c"
    source.write_text('''#include "project_resources.h"
#include "usart.h"
int main(void) {
    if (ProjectMaintenanceUart_Validate() != ProjectMaintenanceUartResult_Mismatch) return 1;
    HostUartHandle correct = {PERIPHERAL, {BAUD, UART_WORDLENGTH_8B,
        UART_PARITY_NONE, UART_STOPBITS_1, UART_MODE_TX_RX, UART_HWCONTROL_NONE}};
    HANDLE = correct;
    if (ProjectMaintenanceUart_Validate() != ProjectMaintenanceUartResult_Ok) return 2;
    for (unsigned i = 0; i < 7U; i++) {
        HANDLE = correct;
        if (i == 0U) HANDLE.Instance = 0U;
        if (i == 1U) HANDLE.Init.BaudRate++;
        if (i == 2U) HANDLE.Init.WordLength++;
        if (i == 3U) HANDLE.Init.Parity++;
        if (i == 4U) HANDLE.Init.StopBits++;
        if (i == 5U) HANDLE.Init.Mode++;
        if (i == 6U) HANDLE.Init.HwFlowCtl++;
        if (ProjectMaintenanceUart_Validate() != ProjectMaintenanceUartResult_Mismatch) return 3;
    }
    return 0;
}
'''.replace("PERIPHERAL", peripheral).replace("BAUD", str(baud) + "U").replace("HANDLE", handle), encoding="utf-8")
    executable = tmp_path / "uart_guard.exe"
    args = _compiler(project)
    # This fixture owns usart.h; unrelated nested Host fixtures also have
    # an Inc/usart.h and must not take precedence over this explicit choice.
    command = args[:1] + ["-I", str(fixture)] + args[1:] + [str(source),
        str(project / "Generated/Src/project_resources.c"),
        str(fixture / "host_uart_state.c"), "-o", str(executable)]
    for args in (command, [str(executable)]):
        result = subprocess.run(args, capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stdout + result.stderr
