import {spawnSync} from 'node:child_process';
for(const args of [['scripts/python.mjs','-m','pytest','tests/test_backend.py','-q'],['--test','tests/compat-v9.test.mjs','tests/owner-v9.test.mjs']]) {
  const result=spawnSync(process.execPath,args,{stdio:'inherit',env:process.env});
  if(result.status!==0)process.exit(result.status||1);
}
