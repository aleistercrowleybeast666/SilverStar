import json, os, re, shutil, subprocess
from pathlib import Path

import pytest
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.generator.source_graph import SourceGraph_Resolve


def function_extract(source, signature):
    start=source.index(signature)
    opening=source.index("{",start)
    depth=1; end=opening+1
    while depth:
        depth+=(source[end]=="{")-(source[end]=="}")
        end+=1
    return source[start:end]+"\n"


@pytest.mark.parametrize("fusion", (0,1,2))
def test_actual_dispatch_reports_rejection_and_does_not_clear_mission_fault(tmp_path,workspace_root,fusion):
    compiler=shutil.which("gcc")
    assert compiler is not None
    service=FccgService(workspace_root)
    model=service.ReferenceProject_Create("RejectPublication")
    project=tmp_path/"generated"
    service.Project_Save(model,project,confirm_dangerous=True)
    app=(project/"APP/Src/ins_task.c").read_text(encoding="utf-8")
    functions=""
    for name in ("InsTask_NavigationDiagnosticsApply", "InsTask_DiagnosticsPublish"):
        functions+=function_extract(app,"static void "+name+"(")
    functions+='static void InsTask_OutputPublish(void) { s_published_output=s_output; InsTask_DiagnosticsPublish(); }\n'
    functions+=function_extract(app,"static void InsTask_PureOutputPublish(")
    functions+=function_extract(app,"static void InsTask_PureRecordWrite(")
    functions+='static void InsTask_InertialOutputsPublish(const InsImuSample *s,const InsState *state) { (void)s; s_predictions++; if (TEST_FUSION==SYSTEM_FUSION_NONE) InsTask_PureOutputPublish(state); else InsTask_DiagnosticsPublish(); }\n'
    functions+=function_extract(app,"static void InsTask_InputReject(")
    functions+=function_extract(app,"static void InsTask_Propagate(")
    fixture=(workspace_root/"tests/fixtures/inertial_rejection_publication.c").read_text(encoding="utf-8")
    path=tmp_path/"publication.c"
    path.write_text(fixture.replace("/* REAL_FUNCTIONS: inserted from the generated application, not reimplemented. */",functions),encoding="utf-8")
    graph=SourceGraph_Resolve(model,service.catalog)
    sources=("Algorithm/INS/Coning2Sculling2/Src/ins_mechanization.c",
             "Algorithm/Common/Src/attitude_frame.c","Common/Src/silverstar_assert.c")
    output=tmp_path/"publication.exe"
    command=[compiler,"-std=c11","-O2","-Wall","-Wextra","-Werror",f"-DTEST_FUSION={fusion}",
             "-include",str(project/"Generated/Inc/project_flight_config.h"),
             *("-I"+str(project/p) for p in graph.include_dirs),
             *(str(project/p) for p in sources),str(path),"-lm","-o",str(output)]
    env=dict(os.environ,TEMP=str(tmp_path),TMP=str(tmp_path))
    (tmp_path/"command.json").write_text(json.dumps(command,indent=2),encoding="utf-8")
    compiled=subprocess.run(command,env=env,capture_output=True,text=True)
    (tmp_path/"compile.log").write_text(compiled.stdout+compiled.stderr,encoding="utf-8")
    assert compiled.returncode==0, compiled.stdout+compiled.stderr
    result=subprocess.run([str(output)],env=env,capture_output=True,text=True)
    (tmp_path/"run.log").write_text(result.stdout+result.stderr,encoding="utf-8")
    assert result.returncode==0,result.stdout+result.stderr
