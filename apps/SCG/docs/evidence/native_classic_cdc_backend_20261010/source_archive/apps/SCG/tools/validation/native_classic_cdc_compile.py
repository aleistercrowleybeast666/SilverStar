"""CLI for shared isolated native compile engine; not formal generation."""
from pathlib import Path
import argparse
import sys
SCG=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(SCG/"src"))
from silverstar_fccg.build.native_compile import NativeCompile_Run

if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input",type=Path,required=True)
    parser.add_argument("--device-facts",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--spi",required=True)
    parser.add_argument("--gpio",nargs="+",required=True)
    parser.add_argument("--toolchain-prefix",default="arm-none-eabi-")
    parser.add_argument("--reviewed-hal",action="store_true",help="Private recognized HAL derivatives, originals preserved; not runtime acceptance")
    parser.add_argument("--clock-hz",type=int,help="Private linked native SysTick clock probe; not a Ground runtime")
    parser.add_argument("--runtime-project",type=Path,help="Read-only isolated candidate configuration; native Ground runtime experiment, not acceptance")
    parser.add_argument("--native-timer-probe",action="store_true",help="Private actual TIM1 clock/HAL/config probe only; not a Ground runtime")
    NativeCompile_Run(parser.parse_args())
