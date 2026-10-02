from pathlib import Path
import sys
sys.dont_write_bytecode=True
repo=Path(r'D:\python_software\SilverStar\.work\FlightStateTelemetryHotfix_20261002')
workspace=Path(__file__).parent
old=workspace/'m0_golden_host.c';(repo/'.work/m0_golden/fixture_first_invalid_status.c').write_bytes(old.read_bytes())
new=workspace/'m0_golden_host_v2.c';new.write_text(old.read_text(encoding='utf8').replace('Air_StatusBuild(42U,3U,','Air_StatusBuild(42U,9U,'),encoding='utf8')
source=(workspace/'fs_m0_golden.py').read_text(encoding='utf8').replace("'.work/m0_golden'","'.work/m0_golden_v2'").replace("'m0_golden_host.c'","'m0_golden_host_v2.c'").replace('202a03785634120100','202a09785634120100')
exec(compile(source,str(workspace/'fs_m0_golden.py'),'exec'))
