from collections import Counter
import json
from pathlib import Path
import re
out=Path(__file__).resolve().parent
result={}
for name in ('pre3','flp_native_final','flp_worker_final','gnss_menus_post','flp_combined_v2','flp_combined_v3','path_gui_post','flp_combined_v4'):
    content=(out/(name+'.log')).read_text(encoding='utf8',errors='replace')
    messages=Counter(re.findall(r'QT (Qt\w+Msg): ([^\n\r]+)',content))
    result[name]={
       'messages':[{'severity':k[0],'text':k[1],'count':v} for k,v in sorted(messages.items())],
       'basic_timer_warning_count':sum(v for k,v in messages.items() if 'QBasicTimer' in k[1]),
       'fatal_message_count':sum(v for k,v in messages.items() if k[0]=='QtFatalMsg'),
       'native_frame_count':len(re.findall(r'^NATIVE ',content,re.M)),
    }
(out/'qt_messages.json').write_text(json.dumps(result,indent=2),encoding='utf8')
print(json.dumps({k:{'timers':v['basic_timer_warning_count'],'fatal':v['fatal_message_count']} for k,v in result.items()}))
