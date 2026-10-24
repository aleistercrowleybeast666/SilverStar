"""Exercise descriptor imports with exactly the standalone bundle's data files."""
import ast
from pathlib import Path
import shutil
import subprocess
import sys


def test_standalone_bundle_contains_both_diagnostic_contracts(tmp_path):
    app = Path(__file__).resolve().parents[1]
    spec = app / 'SilverStar_GSHC.spec'
    tree = ast.parse(spec.read_text(encoding='utf-8'))
    assignments = [node for node in tree.body if isinstance(node, ast.Assign)
                   and any(isinstance(target, ast.Name) and target.id in {'shared', 'datas'}
                           for target in node.targets)]
    namespace = {'Path': Path, 'SPECPATH': str(app)}
    exec(compile(ast.Module(body=assignments, type_ignores=[]), str(spec), 'exec'), namespace)
    package = tmp_path / 'silverstar_diagnostics'
    package.mkdir()
    for path in (app.parent / 'SCG/src/silverstar_diagnostics').glob('*.py'):
        shutil.copyfile(path, package / path.name)
    for source, destination in namespace['datas']:
        target = tmp_path / destination / Path(source).name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    code = ('import sys; sys.path.insert(0, sys.argv[1]); '
            'from silverstar_diagnostics.project_descriptor import ProjectDescriptor_Create, ProjectDescriptor_Validate; '
            'value=ProjectDescriptor_Create("Bundle fixture", "STM32F407VET6"); '
            'assert ProjectDescriptor_Validate(value)["state"] == "pending_build"')
    result = subprocess.run([sys.executable, '-I', '-B', '-c', code, str(tmp_path)],
                            cwd=tmp_path, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
