import {spawnSync} from 'node:child_process';
import fs from 'node:fs';
const python=process.env.PYTHON||(fs.existsSync('.venv/bin/python')?'.venv/bin/python':fs.existsSync('.venv/Scripts/python.exe')?'.venv/Scripts/python.exe':'python');
const result=spawnSync(python,process.argv.slice(2),{stdio:'inherit',env:process.env});
if(result.error)console.error(result.error.message);
process.exit(result.status??1);
