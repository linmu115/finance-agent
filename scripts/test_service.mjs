import { spawnSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const python = process.env.FINANCE_PYTHON || path.join(root, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
const result = spawnSync(python, ['-m', 'unittest', 'discover', '-s', 'service/tests', '-v'], {
  cwd: root, stdio: 'inherit', windowsHide: true,
  env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
});
if (result.error) console.error(result.error.message);
process.exit(result.status ?? 1);
