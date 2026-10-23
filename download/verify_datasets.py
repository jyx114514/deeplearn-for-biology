from pathlib import Path
import json, csv, gzip
from collections import Counter
import numpy as np
root=Path(__file__).resolve().parent
records=json.loads((root/'download_manifest.json').read_text(encoding='utf-8-sig'))
counts=Counter()
for r in records:
 p=Path(r['path'])
 if not p.exists() or p.stat().st_size!=r['expected_bytes']:
  raise RuntimeError(f'Missing or incomplete: {p}')
 counts[p.relative_to(root).parts[0]]+=1
for p in (root/'chapter_03_dna').glob('*.csv'):
 with p.open(encoding='utf-8-sig',newline='') as f:
  reader=csv.DictReader(f)
  if not {'sequence','label'}.issubset(reader.fieldnames or []):
   raise ValueError(f'Unexpected columns: {p}: {reader.fieldnames}')
  n=sum(1 for row in reader)
  print(p.name,n,'rows')
for p in (root/'chapter_04_graphs').rglob('*.gz'):
 with gzip.open(p,'rb') as f:
  while f.read(1024*1024): pass
 print('GZIP_OK',p.name)
labels=np.load(root/'chapter_06_localization'/'labels.npy',allow_pickle=True)
images=np.memmap(root/'chapter_06_localization'/'images.npy',dtype='float32',mode='r').reshape(-1,100,100,1)
assert len(labels)==len(images),(labels.shape,images.shape)
for i in (0,len(images)//2,len(images)-1):
 assert np.isfinite(images[i]).all(),i
print('LOCALIZATION',images.shape,labels.shape)
print('VERIFIED',dict(counts))
