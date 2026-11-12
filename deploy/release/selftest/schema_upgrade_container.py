"""Real N-1 schema contract in a disposable container; no production endpoints."""
import os
from pathlib import Path
import subprocess


def main():
    if not Path('/.dockerenv').exists() or os.geteuid() != 0:
        raise SystemExit('disposable container required')
    root = Path('/test-schema')
    root.mkdir()
    config = root/'gitconfig'
    config.write_text('[safe]\n directory=/repo\n directory=/repo/.git\n')
    env = dict(os.environ,GIT_CONFIG_GLOBAL=str(config))
    def run(args):
        proc = subprocess.run(args,env=env,capture_output=True,text=True,timeout=360)
        if proc.returncode:
            raise RuntimeError(proc.stdout + proc.stderr)
        return proc.stdout
    run(['pg_ctlcluster','16','main','start'])
    run(['runuser','-u','postgres','--','psql','-c',"ALTER ROLE postgres PASSWORD 'local-schema-test'"])
    clone = root/'repo'
    run(['git','clone','-q','--shared','/repo',str(clone)])
    head = run(['git','-C',str(clone),'rev-parse','HEAD']).strip()
    result = run(['/opt/test-venv/bin/python','/repo/tools/ci/migration_upgrade_test.py',
                  '--repo',str(clone),'--base','cd7b66837bf63bd2a0f5e4d53c80cb3964e6480f','--head',head,
                  '--admin-url','postgresql://postgres:local-schema-test@127.0.0.1:5432/postgres'])
    print(result,flush=True)


if __name__ == '__main__':
    main()
