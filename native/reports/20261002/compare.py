import sys, json, os, random, hashlib
from pathlib import Path
from datetime import datetime, timezone
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))
from run import execute, measure
root=HERE.parent.parent / 'out'
names=['barrier-baseline','u64-indices','static-lanes','lane-absorb']
reports={n:json.loads((root/(n+'-20261002')/'results.json').read_text()) for n in names}
assert all(r['complete'] for r in reports.values())
assert len({r['compiler_sha256'] for r in reports.values()})==1
commands={n:[root/(n+'-20261002')/'O2/keccak_bench'] for n in names}
for n,c in commands.items():
 assert hashlib.sha256(c[0].read_bytes()).hexdigest()==reports[n]['executables']['fe-O2']['sha256']
commands['rust-tiny']=[root/'lane-absorb-20261002/rust-keccak','tiny']
commands['rustcrypto']=[root/'lane-absorb-20261002/rust-keccak','rustcrypto']
cpu=min(os.sched_getaffinity(0));os.sched_setaffinity(0,{cpu})
record={'complete':False,'created':datetime.now(timezone.utc).isoformat(),'cpu':cpu,'compiler_sha256':reports[names[0]]['compiler_sha256'],'executable_sha256':{n:hashlib.sha256(c[0].read_bytes()).hexdigest() for n,c in commands.items()},'source_reports':{n:str(root/(n+'-20261002')/'results.json') for n in names},'measurements':[]}
out=root/'alternating-20261002.json'
for batch in range(3):
 for index,length in enumerate([0,32,136,4096,65536]):
  data=random.Random(length).randbytes(length)
  expected=execute(commands['rust-tiny'],[(data,1,0)])[0][1]
  entries=list(commands.items());rotation=(batch+index)%len(entries)
  for name,command in entries[rotation:]+entries[:rotation]:
   row=measure(command,data,expected,reports[names[0]]['host']['clock_ticks_per_second'],7,50)
   row.update(batch=batch,implementation=name)
   record['measurements'].append(row)
   out.write_text(json.dumps(record,indent=2)+'\n')
 print('batch',batch,'finished',flush=True)
record['complete']=True
out.write_text(json.dumps(record,indent=2)+'\n')
