from pathlib import Path
task=Path(__file__).parent
for old,new in [('backend_pytest.py','daily_backend_pytest.py'),('run_usb_gui_tests.py','run_daily_usb_gui.py'),('run_gui_preserved_regression.py','run_daily_regression.py'),('run_usb_async_tests.py','run_daily_async.py')]:
    s=(task/old).read_text(encoding='utf8')
    s=s.replace('D:/python_software/SilverStar/.work/ccdi','D:/python_software/SilverStar')
    s=s.replace('D:\\python_software\\SilverStar\\.work\\ccdi','D:\\python_software\\SilverStar')
    s=s.replace("task/'backend_pytest.py'","task/'daily_backend_pytest.py'")
    # Refresh tests consume the newly generated daily output, not isolated receipts.
    if old=='run_usb_async_tests.py':s=s.replace("task/'ug08-build-index.jsonl'","task/'dm01-build-index.jsonl'")
    (task/new).write_text(s,encoding='utf8',newline='\n')
print('Created daily-path validation runners; no repository source modifications')
