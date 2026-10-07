import json
from pathlib import Path
root=Path('apps/FLP/src/silverstar_flp/i18n')
messages={
 'en_US': 'Windows could not access the long project/artifact path. Save to a shorter folder or use a shorter project filename, then retry. This save has not completed.',
 'zh_CN': 'Windows无法访问过长的工程/工件路径。请缩短保存目录或工程文件名后重试；本次保存未完成。',
}
for language,message in messages.items():
    path=root/(language+'.json')
    catalog=json.loads(path.read_text(encoding='utf8'))
    catalog['error.code.project_save_path_too_long']=message
    path.write_text(json.dumps(catalog,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
