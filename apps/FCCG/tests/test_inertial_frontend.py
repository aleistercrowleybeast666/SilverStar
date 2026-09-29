"""Exercise the common frontend without creating or updating navigation state."""
import os
import re
import subprocess

from silverstar_fccg.app.service import FccgService


def test_inertial_frontend_and_selected_navigation(tmp_path, workspace_root):
    service = FccgService(workspace_root)
    project = tmp_path / 'generated'
    service.Project_Save(service.ReferenceProject_Create('InertialFrontend'), project,
                         confirm_dangerous=True)
    output = project / 'build/FCCG/Host/InertialFrontend'
    output.mkdir(parents=True)
    env = dict(os.environ, TEMP=str(output), TMP=str(output))
    env['PATH'] = 'D:/msys64/ucrt64/bin;' + env.get('PATH', '')
    script = (project / 'Tests/Host/run_tests.ps1').read_text(encoding='utf-8')
    includes = re.findall(r'"-I\$repoRoot\\([^"\n]+)"', script)
    sources = ['Algorithm/INS/Coning2Sculling2/Src/ins_mechanization.c',
               'Algorithm/Common/Src/attitude_frame.c', 'Common/Src/silverstar_assert.c']
    command = ['D:/msys64/ucrt64/bin/gcc.exe', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
               '-include', str(project / 'Generated/Inc/project_flight_config.h')]
    command += ['-I' + str(project / path.replace('\\', '/')) for path in includes]
    command += [str(project / path) for path in sources]
    command += [str(workspace_root / 'tests/fixtures/inertial_frontend.c'),
                '-lm', '-o', str(output / 'frontend.exe')]
    compiled = subprocess.run(command, capture_output=True, text=True, env=env)
    assert compiled.returncode == 0, compiled.stdout + compiled.stderr
    subprocess.run([str(output / 'frontend.exe')], env=env, check=True)

    # Compile the actual dispatch body with a poison Pure INS entry. A KF6 input
    # must reach the frontend and publish once, with no navigation or Pure log.
    app = (project / 'APP/Src/ins_task.c').read_text(encoding='utf-8')
    body = app[app.index('static void InsTask_Propagate('):app.index('\nvoid AppTask_Ins(')]
    fixture = r'''
#include <stddef.h>
#include <stdint.h>
#define SYSTEM_FUSION_NONE 0U
#define SYSTEM_FUSION_KF6 1U
#define SYSTEM_FUSION_ESKF15 2U
#define SYSTEM_FUSION_ALGORITHM SYSTEM_FUSION_KF6
#define SYSTEM_MECHANIZATION_SUBSAMPLE_COUNT 2U
#define SILVERSTAR_PROTOCOL_LOGGING_ENABLED 1U
#define SILVERSTAR_ASSERT_OBJECT(p,t,m) ((void)(p))
#define INS_INERTIAL_UPDATE_READY 0
typedef struct { uint8_t quality_flags; int value; } InsImuSample;
typedef int InsAlgorithmSample;
typedef int InsState;
typedef struct { unsigned int sample_count; } InertialContext;
static struct { InertialContext inertial; int pure_ins; } s_navigation_input;
static unsigned int input_count, navigation_count, publication_count, pure_log_count;
static unsigned int quality_count, body_pair_count;
static void SystemNavigationHealth_ImuQualityRecord(uint8_t flags)
{ (void)flags; quality_count++; }
static void InsTask_BodyPairBuild(const int *s) { (void)s; body_pair_count++; }
static int InsTask_SampleCorrect(const InsImuSample *a, int *b) { *b=a->value; return 1; }
static int InsInertial_Update(InertialContext *c, const int *s, int *o)
{ (void)c; input_count++; *o=*s; return 0; }
static int InsMechanization_Update(int *c, const int *s, int *o)
{ (void)c; (void)s; (void)o; navigation_count++; return 1; }
static void InsTask_InertialOutputsPublish(const InsImuSample *s, const int *o)
{ (void)s; (void)o; publication_count++; }
static void InsTask_PureRecordWrite(const InsImuSample *s, const int *o)
{ (void)s; (void)o; pure_log_count++; }
'''
    fixture += body + r'''
int main(void) {
    InsImuSample sample={0U, 1};
    InsTask_Propagate(&sample);
    sample.quality_flags = 0x02U;
    InsTask_Propagate(&sample);
    return input_count != 1 || publication_count != 1 || navigation_count ||
        pure_log_count || body_pair_count || quality_count != 2;
}
'''
    path = output / 'dispatch.c'
    path.write_text(fixture, encoding='utf-8')
    subprocess.run([command[0], '-std=c11', '-Wall', '-Wextra', '-Werror', str(path),
                    '-o', str(output / 'dispatch.exe')], env=env, check=True)
    subprocess.run([str(output / 'dispatch.exe')], env=env, check=True)
