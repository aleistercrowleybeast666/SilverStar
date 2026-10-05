"""Integrate a clean CubeMX Flight entry without editing the import snapshot."""

import re


def CompactFlightMain_Integrate(content: bytes) -> bytes:
    source = content.decode("utf-8-sig")
    sections = {
        "Includes": '\n#include "FreeRTOS.h"\n#include "task.h"\n#include "app_tasks.h"\n#include "system_startup.h"\n',
        "2": """
  {
    SystemStartupResult result = SystemStartup_Run();
    if (SystemStartup_ResultIsFatal(result) != 0U)
    {
      Error_Handler();
    }
  }
  if (AppTasks_Init() != AppTasksInitResult_Ok)
  {
    Error_Handler();
  }
  vTaskStartScheduler();
  Error_Handler();
""",
    }
    for section, body in sections.items():
        start = f"/* USER CODE BEGIN {section} */"
        end = f"/* USER CODE END {section} */"
        pattern = re.compile(re.escape(start) + r"(.*?)" + re.escape(end), re.DOTALL)
        matches = tuple(pattern.finditer(source))
        if len(matches) != 1 or matches[0].group(1).strip():
            raise ValueError(f"Compact Flight requires one empty CubeMX USER CODE {section} section")
        source = pattern.sub(lambda _: start + body + end, source, count=1)
    return source.encode("utf-8")
