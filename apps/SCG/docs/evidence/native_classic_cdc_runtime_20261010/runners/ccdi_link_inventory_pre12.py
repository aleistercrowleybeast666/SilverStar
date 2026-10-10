from pathlib import Path
import json
root=Path('C:/Users/chdxm/AppData/Local/Temp/sscdc-ground-f103-12a')
reports=json.loads((root/'build/native-artifact-report.json').read_text())
for report in reports:
    for member in report['linked_libraries']:
        assert member['object'] != '*', 'Linker wildcard is not a retained archive member: '+str(member)
        assert Path(member['archive']).is_file(), 'Archive path lost its spaces: '+str(member)
        assert 'mallocr' not in member['object'], 'Discarded heap member incorrectly reported as retained'
