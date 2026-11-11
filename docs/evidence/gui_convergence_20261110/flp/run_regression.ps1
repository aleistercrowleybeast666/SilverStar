param([string]$Tag = 'full', [string[]]$Nodes = @())
$ErrorActionPreference = 'Stop'
$repo = 'D:/python_software/SilverStar'
$task = "$repo/.work/gui-convergence-20261110/flp"
$inputRoot = "$task/inputs"
$traceRoot = "$repo/.work/gui-convergence-20261110/horizon-traces-final"
$env:PATH = 'D:/msys64/ucrt64/bin;' + $env:PATH
$env:QT_QPA_FONTDIR = 'C:/Windows/Fonts'
$env:PYTEST_PLUGINS = 'tests.qt_exception_probe'
$env:SS_FLP_QT_TRACE = "$task/$Tag-qt-exceptions.log"
$env:SILVERSTAR_FCCG_ROOT = "$repo/apps/SCG"
$env:SILVERSTAR_ESKF_GENERATED = "$inputRoot/eskf-replay"
$env:SILVERSTAR_GENERATED_DECODER_EXISTING = "$inputRoot/aggregation-existing"
$env:SILVERSTAR_GENERATED_DECODER_IMPORTED = "$inputRoot/aggregation-imported"
$env:SILVERSTAR_GENERATED_DECODER_PURE = "$inputRoot/pure"
$env:SILVERSTAR_GENERATED_DECODER_ESKF = "$inputRoot/aggregation-eskf"
$env:SILVERSTAR_FCCG_GENERATED = "$inputRoot/joint"
$env:SILVERSTAR_C_GOLDEN = "$task/producers/joint2/navigation.sslog"
$env:SILVERSTAR_SS_TEST_0_ROOT = "$inputRoot/codec-golden"
$env:SILVERSTAR_SF6_ACTUAL_ROOT = $inputRoot
$env:SILVERSTAR_SF6_LOG = '../producers/sf6.sslog'
$env:SILVERSTAR_SF6_PROJECT = 'sf6'
$env:SILVERSTAR_CURRENT_KF_TRACE = "$task/producers/kf.jsonl"
$env:SILVERSTAR_CURRENT_KF_DECODER = "$inputRoot/existing/FLP_Software_existing.ssdecoder"
$env:SILVERSTAR_CURRENT_ESKF_TRACE = "$task/producers/eskf.sslog"
$env:SILVERSTAR_CURRENT_ESKF_DECODER = "$inputRoot/eskf/FLP_Software_eskf.ssdecoder"
$env:SILVERSTAR_HORIZON_TRACE_ROOT = $traceRoot
$env:SILVERSTAR_HORIZON_RECORDED_TRACE_ROOT = $traceRoot
$env:SILVERSTAR_HORIZON_NATIVE_TRACE_ROOT = "$repo/.work/gui-convergence-20261110/native-horizon-traces"
$env:SILVERSTAR_HORIZON_KF_STAGE_PROJECT = "$traceRoot/kf_backend_config0/project"
$env:SILVERSTAR_HORIZON_STAGE_PROJECT = "$traceRoot/eskf_backend_config0/project"
$env:SS_FLP_SOURCE = (git rev-parse HEAD).Trim() + '; FLP traced snapshot in ' + $Tag + '-environment.json'
$evidence = @{}
Get-ChildItem Env: | Where-Object { $_.Name -match '^(SILVERSTAR_|SS_FLP_|QT_QPA_|PYTEST_PLUGINS)' } | ForEach-Object { $evidence[$_.Name] = $_.Value }
$evidence | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath "$task/$Tag-environment.json" -Encoding utf8
& "$repo/.venv/Scripts/python.exe" "$repo/docs/evidence/release_candidate_20261103/flp/suite-review/run_flp_suite.py" --repo $repo --work "$repo/.work/gcf-$Tag" --evidence $task --tag $Tag --max-continuations 0 @Nodes
exit $LASTEXITCODE
