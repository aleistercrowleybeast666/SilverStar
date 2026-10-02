from pathlib import Path
import sys
sys.dont_write_bytecode=True
workspace=Path(__file__).parent
source=(workspace/'fs_m0_unchanged.py').read_text(encoding='utf8').replace("'.work/m0_final_evidence'","'.work/m0_final_v2_evidence'").replace("'.work/m0_final'","'.work/m0_final_v2'")
exec(compile(source,str(workspace/'fs_m0_unchanged.py'),'exec'))
source=(workspace/'fs_m0_golden.py').read_text(encoding='utf8').replace("'.work/m0_golden'","'.work/m0_final2_golden'").replace("'m0_golden_host.c'","'m0_golden_host_v2.c'").replace('202a03785634120100','202a09785634120100').replace("'.work/m0_final/Flight_Controller'","'.work/m0_final_v2/Flight_Controller'")
exec(compile(source,str(workspace/'fs_m0_golden.py'),'exec'))
