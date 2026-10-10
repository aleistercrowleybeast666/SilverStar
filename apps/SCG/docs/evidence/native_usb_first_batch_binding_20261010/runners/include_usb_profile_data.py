from pathlib import Path
root = Path(r'D:\python_software\SilverStar\.work\ccdi')
path = root/'apps/SCG/pyproject.toml'
text=path.read_text(encoding='utf-8')
old='silverstar_fccg = ["i18n/*.json", "ui/assets/*.svg"]'
assert old in text
path.write_text(text.replace(old, 'silverstar_fccg = ["i18n/*.json", "ui/assets/*.svg", "hardware/usb_profiles/*.json"]'), encoding='utf-8', newline='\n')
print('USB backend profile JSON included in package data')
