from pathlib import Path
import ast
p=Path('D:/python_software/SilverStar/.work/ccdi/apps/SCG/tests/test_native_runtime.py')
s=p.read_text(encoding='utf-8')
s=s.replace("harness=harness.replace('static uint8_t radio_not_initialized,radio_unverified;\nstatic uint8_t platform_started;',", "harness=harness.replace('static uint8_t radio_not_initialized,radio_unverified;',")
s=s.replace("'static uint8_t radio_not_initialized,radio_unverified;\nstatic uint8_t platform_started;\\nstatic uint8_t transport_bad_init,transport_bad_process;')", "'static uint8_t radio_not_initialized,radio_unverified;\\nstatic uint8_t transport_bad_init,transport_bad_process;')")
ast.parse(s)
p.write_text(s,encoding='utf-8',newline='\n')
print('Python collection literal repaired; AST valid')
