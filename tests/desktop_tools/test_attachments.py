from pathlib import Path
import pytest
from silverstar_fccg.project.folder_contract import AttachmentsDirectory_Ensure, ProjectRoot_Save
from silverstar_fccg.project.model import ProjectModel, ProjectIdentity


def test_new_project_has_plain_attachments(tmp_path):
    root=tmp_path/'project'
    model=ProjectModel(ProjectIdentity('Recovery_Test'),'silverstar.core.0_1_0',
        'silverstar.mcu.stm32f407vet6','silverstar.board.silverstar_0_5','silverstar.os.freertos_11_3_0')
    ProjectRoot_Save(model,root,create_new=True)
    assert all((root/name).is_dir() for name in ('Flight_Controller','Ground_Station','Log','Attachments'))


def test_old_project_ensure_preserves_arbitrary_manual_files(tmp_path):
    root=tmp_path/'old';root.mkdir()
    directory=AttachmentsDirectory_Ensure(root)
    file=directory/'用户手动资料.exe';original=b'never execute arbitrary attachment'
    file.write_bytes(original)
    assert AttachmentsDirectory_Ensure(root)==directory
    assert file.read_bytes()==original


def test_existing_name_collision_does_not_overwrite(tmp_path):
    target=tmp_path/'Attachments';target.write_bytes(b'user input')
    with pytest.raises(FileExistsError):AttachmentsDirectory_Ensure(tmp_path)
    assert target.read_bytes()==b'user input'
