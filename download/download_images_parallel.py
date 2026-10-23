from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
import requests,json,time,threading,os
root=Path(__file__).resolve().parent/'chapter_06_localization'
target=root/'images.npy'; part=root/'images.npy.parallel.part'; state=root/'images.npy.ranges.json'
url='https://assets.deep-learning-for-biology.com/localization/datasets/images.npy'
size=45383680000; chunk=32*1024*1024
if target.exists() and target.stat().st_size==size:
 print('ALREADY_COMPLETE',flush=True);raise SystemExit
if state.exists():
 s=json.loads(state.read_text());prefix=s['prefix'];done=set(s['done'])
else:
 old=root/'images.npy.part';prefix=old.stat().st_size if old.exists() else 0
 if old.exists():old.rename(part)
 else:part.touch()
 done=set()
 with part.open('r+b') as f:f.truncate(size)
 s={'prefix':prefix,'done':[]};state.write_text(json.dumps(s))
ranges=[(i,start,min(start+chunk,size)-1) for i,start in enumerate(range(prefix,size,chunk))]
start_time=time.monotonic(); initial=sum(e-b+1 for i,b,e in ranges if i in done)
def fetch(t):
 i,b,e=t
 for attempt in range(10):
  try:
   with requests.get(url,headers={'Range':f'bytes={b}-{e}','Accept-Encoding':'identity'},stream=True,timeout=(30,90)) as r:
    r.raise_for_status()
    if r.status_code!=206 or not r.headers.get('Content-Range','').startswith(f'bytes {b}-{e}/'):raise RuntimeError('Server range mismatch')
    n=0
    with part.open('r+b',buffering=0) as f:
     f.seek(b)
     for data in r.iter_content(1024*1024):
      if n+len(data)>e-b+1:raise RuntimeError('Oversized range')
      f.write(data);n+=len(data)
    if n!=e-b+1:raise RuntimeError('Incomplete range')
   return i
  except Exception:
   if attempt==9:raise
   time.sleep(min(30,2**attempt))
print('START',size,'prefix',prefix,'completed_ranges',len(done),'workers',8,flush=True)
last=0
with ThreadPoolExecutor(max_workers=8) as pool:
 futures=[pool.submit(fetch,t) for t in ranges if t[0] not in done]
 for fut in as_completed(futures):
  done.add(fut.result());s={'prefix':prefix,'done':sorted(done)}
  tmp=state.with_suffix('.tmp');tmp.write_text(json.dumps(s));tmp.replace(state)
  now=time.monotonic()
  if now-last>=25:
   completed=prefix+sum(e-b+1 for i,b,e in ranges if i in done)
   speed=(completed-prefix-initial)/(now-start_time)/1e6
   print(f'PROGRESS {completed}/{size} {completed/size:.2%} {speed:.2f} MB/s',flush=True);last=now
assert len(done)==len(ranges)
assert part.stat().st_size==size
part.rename(target)
print('IMAGE_DOWNLOAD_COMPLETE',size,flush=True)
