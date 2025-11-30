import pathlib
lines=pathlib.Path('auditor_inference/document_extraction.py').read_text().splitlines()
start=None
for i,l in enumerate(lines):
    if 'def _detect_form_type_from_text' in l:
        start=i
        break
print('start', start)
for j in range(start, min(len(lines), start+40)):
    print(f"{j+1}: {lines[j]}")
