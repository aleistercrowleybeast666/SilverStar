import os
from pathlib import Path

import pytest

from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.workspace import WorkspacePolicyError


@pytest.mark.skipif(os.name != "nt", reason="Windows legacy copy path boundary")
def test_overlong_generation_has_actionable_error_and_no_published_payload(tmp_path: Path, workspace_root):
    service = FccgService(workspace_root)
    model = service.ReferenceProject_Create("LongPathRejection")
    root = tmp_path / ("project_" + "x" * 80)
    before = model.Dictionary_Get()
    with pytest.raises(WorkspacePolicyError, match="WINDOWS_PATH_TOO_LONG.*shorten"):
        service.Project_Save(model, root, confirm_dangerous=True)
    assert model.Dictionary_Get() == before
    assert not (root / "SilverStar.ssproject").exists()
    assert not (root / "APP").exists()
    assert not (root / "Generated").exists()
