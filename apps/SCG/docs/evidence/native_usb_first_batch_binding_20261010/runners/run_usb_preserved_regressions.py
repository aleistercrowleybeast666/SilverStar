from pathlib import Path
script = Path(__file__).with_name('run_backend_regressions.py')
text = script.read_text(encoding='utf-8').replace("label = 'nbr01'", "label = 'ubr01'")
exec(compile(text, str(script), 'exec'), {'__file__': str(script)})
