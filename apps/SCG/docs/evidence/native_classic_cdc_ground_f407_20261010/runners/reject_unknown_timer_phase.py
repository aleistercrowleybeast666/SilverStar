from pathlib import Path
root=Path('D:/python_software/SilverStar/.work/ccdi')
p=root/'apps/SCG/src/silverstar_fccg/generator/native_clock_tim.py'
s=p.read_text(encoding='utf-8')
old='''    function=function.replace(old,\'\'\'uwTimclock = HAL_RCC_GetPCLK2Freq();'''
new='''    function=function.replace(old,\'\'\'if ((clkconfig.APB2CLKDivider != RCC_HCLK_DIV1) &&
      (clkconfig.APB2CLKDivider != RCC_HCLK_DIV2)) { return HAL_ERROR; }
  uwTimclock = HAL_RCC_GetPCLK2Freq();'''
assert s.count(old)==1;s=s.replace(old,new,1)
anchor='    if (timer_hz > 100000000U) { return 0U; }'
new='''    /* This recognized main has only DIV1 reset and DIV2 final clock phases. */
    if ((config.APB2CLKDivider != RCC_HCLK_DIV1) &&
        (config.APB2CLKDivider != RCC_HCLK_DIV2)) { return 0U; }
'''+anchor
assert s.count(anchor)==1;s=s.replace(anchor,new,1)
p.write_text(s,encoding='utf-8',newline='\n')
p=root/'apps/SCG/tests/test_native_clock_tim.py'
s=p.read_text(encoding='utf-8')
s=s.replace('    if (strcmp(argv[1],"bad-clock")==0)',
    '    if (strcmp(argv[1],"bad-divider")==0) { divider=8U; }\n    if (strcmp(argv[1],"bad-clock")==0)',1)
s=s.replace('if (priority==16U || pclk==16500000U ||', 'if (priority==16U || divider==8U || pclk==16500000U ||',1)
s=s.replace("['div1','div2','bad-clock','bad-priority','base-fail','start-fail']", "['div1','div2','bad-clock','bad-divider','bad-priority','base-fail','start-fail']",1)
anchor='    TIM1->PSC=83U;assert(NativeClockPort_SnapshotGet(&sample)==NativeClockResult_InvalidConfiguration);TIM1->PSC=167U;'
assert s.count(anchor)==1
s=s.replace(anchor,"    divider=8U;assert(NativeClockPort_SnapshotGet(&sample)==NativeClockResult_InvalidConfiguration);divider=RCC_HCLK_DIV2;\n"+anchor,1)
p.write_text(s,encoding='utf-8',newline='\n')
print('Private timer recognizes only actual DIV1/DIV2 boot phases; unknown divider rejected with unchanged progress and UIF checks')
