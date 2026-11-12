#!/usr/bin/env python3
"""Run ONLY in a disposable Linux container, as root. No external SSH/DB hosts.

Real installer, Unix accounts, sudo/sshd forced command, PostgreSQL and restic.
The repository is mounted read-only at /repo. All state is under /test and the
container's /etc, /srv and /usr/local/lib. Never run this on an application host.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time


def run(args, *, user=None, check=True, env=None):
    cmd = (['runuser', '-u', user, '--'] if user else []) + list(map(str, args))
    p = subprocess.run(cmd, env=env, text=True, capture_output=True, timeout=180)
    if check and p.returncode:
        raise AssertionError('%s exited %s\n%s\n%s' % (cmd[:5], p.returncode, p.stdout, p.stderr))
    return p


def main():
    if not Path('/.dockerenv').exists() or os.geteuid() != 0 or not Path('/repo/deploy/release').is_dir():
        raise SystemExit('requires a disposable container with read-only /repo mount')
    os.umask(0o022)
    root = Path('/test')
    root.mkdir(exist_ok=True)
    run(['useradd', '-m', '-s', '/bin/sh', 'rastisi'])
    run(['bash', '/repo/deploy/release/install.sh', '--service', 'test-rastisi.service', '--app-user', 'rastisi', '--base', '/srv/rastisi-releases', '--env-file', '/etc/rastisi/test.env', '--port', '18082'])
    assert Path('/usr/local/lib/rastisi/make_dropin.py').is_file()
    run(['visudo', '-cf', '/etc/sudoers.d/rastisi-deploy'])
    run(['usermod', '-p', '*', 'rastisi-deploy'])
    # Local, generated test keys only; no externally configured identity.
    run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', '/test/client_key'])
    ssh_dir = Path('/home/rastisi-deploy/.ssh')
    ssh_dir.mkdir(mode=0o700)
    pub = Path('/test/client_key.pub').read_text().strip()
    (ssh_dir/'authorized_keys').write_text('restrict,command="/usr/bin/python3 /usr/local/lib/rastisi/rastisi_gate.py" ' + pub + '\n')
    os.chmod(ssh_dir/'authorized_keys', 0o600)
    run(['chown', '-R', 'rastisi-deploy:rastisi-deploy', ssh_dir])
    Path('/run/sshd').mkdir(exist_ok=True)
    os.chmod('/run/sshd', 0o755)
    os.chown('/run/sshd', 0, 0)
    run(['ssh-keygen', '-A'])
    snippet = Path('/repo/deploy/release/examples/sshd_config.snippet').read_text()
    Path('/test/sshd.conf').write_text('Port 2222\nListenAddress 127.0.0.1\nHostKey /etc/ssh/ssh_host_ed25519_key\nPidFile /test/sshd.pid\nUsePAM no\nPermitRootLogin no\n' + snippet)
    run(['/usr/sbin/sshd', '-t', '-f', '/test/sshd.conf'])
    run(['/usr/sbin/sshd', '-f', '/test/sshd.conf'])
    hostkey = Path('/etc/ssh/ssh_host_ed25519_key.pub').read_text().split()
    Path('/test/known_hosts').write_text('[127.0.0.1]:2222 ' + ' '.join(hostkey[:2]) + '\n')
    ssh = ['ssh', '-p', '2222', '-i', '/test/client_key', '-o', 'IdentitiesOnly=yes', '-o', 'StrictHostKeyChecking=yes', '-o', 'UserKnownHostsFile=/test/known_hosts', '-o', 'BatchMode=yes', 'rastisi-deploy@127.0.0.1']
    version = json.loads(run(ssh + ['version']).stdout)
    assert version['tooling'] == '2'
    assert run(ssh + ['id'], check=False).returncode != 0
    assert run(ssh, check=False).returncode != 0
    assert run(ssh[:-1] + ['-o', 'ExitOnForwardFailure=yes', '-R', '0:localhost:9', ssh[-1], 'version'], check=False).returncode != 0
    assert run(['sudo', '-n', '-u', 'root', '/usr/bin/id'], user='rastisi-deploy', check=False).returncode != 0
    assert run(['sudo', '-n', '-u', 'rastisi', '/usr/bin/python3', '/usr/local/lib/rastisi/rastisi_app_task.py', 'who'], user='rastisi-deploy').returncode == 0
    print('PASS installed SSH: version, forced-command rejection, no interactive shell, no port forwarding, restricted sudo', flush=True)

    run(['pg_ctlcluster', '16', 'main', 'start'])
    run(['psql', '-v', 'ON_ERROR_STOP=1', '-c', "CREATE ROLE rastisi_app LOGIN PASSWORD 'local-only-app'; CREATE ROLE rastisi_drill LOGIN PASSWORD 'local-only-drill' CREATEDB NOSUPERUSER NOCREATEROLE;"], user='postgres')
    run(['createdb', '-O', 'rastisi_app', 'rastisi_test'], user='postgres')
    pg_env = dict(os.environ, PGHOST='127.0.0.1', PGUSER='rastisi_app', PGPASSWORD='local-only-app', PGDATABASE='rastisi_test')
    run(['psql', '-v', 'ON_ERROR_STOP=1', '-c', "CREATE TABLE stores_store(id serial primary key,name text); CREATE TABLE orders_order(id serial primary key,total int); CREATE TABLE auth_user(id serial primary key,username text); INSERT INTO stores_store(name) VALUES('local-canary-shop'); INSERT INTO orders_order(total) SELECT g FROM generate_series(1,300) g; INSERT INTO auth_user(username) VALUES('local-canary-user');"], env=pg_env)
    for name in ['media', 'backup-state', 'restic']:
        (root/name).mkdir()
    (root/'media/canary.txt').write_text('local synthetic customer media')
    Path('/etc/rastisi/test.env').write_text('DATABASE_URL=postgresql://rastisi_app:local-only-app@127.0.0.1:5432/rastisi_test\n')
    run(['chown', 'rastisi:rastisi', '/etc/rastisi/test.env'])
    os.chmod('/etc/rastisi/test.env', 0o600)
    (root/'password').write_text('local-test-restic-password')
    os.chmod(root/'password', 0o600)
    run(['chown', '-R', 'rastisi:rastisi', root/'media', root/'backup-state', root/'restic', root/'password'])
    Path('/etc/rastisi/backup.conf').write_text('[backup]\nenv_file=/etc/rastisi/test.env\nstate_dir=/test/backup-state\nmedia_root=/test/media\nrestic_repository=/test/restic\nrestic_password_file=/test/password\nconfig_files=/etc/rastisi/test.env\ndrill_admin_url=postgresql://rastisi_drill:local-only-drill@127.0.0.1:5432/postgres\ncritical_tables=stores_store,orders_order,auth_user\nretention=yes\ncheck_read_data_subset=100%\n')
    run(['restic', '-r', '/test/restic', '--password-file', '/test/password', 'init'], user='rastisi')
    backup = ['python3', '/usr/local/lib/rastisi-backup/rastisi_backup.py']
    for verb in ['run', 'verify', 'restore-drill', 'status']:
        result = run(backup + [verb], user='rastisi')
        print('PASS installed backup ' + verb, flush=True)
    record = Path('/test/backup-state/last_backup.json')
    assert json.loads(run(['cat', record], user='rastisi-deploy').stdout)['verified']
    assert run(['cat', '/etc/rastisi/test.env'], user='rastisi-deploy', check=False).returncode != 0
    assert json.loads(Path('/test/backup-state/last_restore_drill.json').read_text())['ok']
    assert run(['psql', '-At', '-c', 'SELECT count(*) FROM orders_order'], env=pg_env).stdout.strip() == '300'
    assert run(['psql', '-At', '-c', "SELECT count(*) FROM pg_database WHERE datname LIKE 'rastisi_test_drill_%'"], user='postgres').stdout.strip() == '0'
    print('PASS backup visibility: deploy reads state but cannot read credentials; 300 synthetic orders unchanged; scratch DB removed', flush=True)

    if Path('/opt/test-venv/lib').is_dir():
        # Run a real non-atomic MigrationExecutor operation: SQL commits before
        # failure and no django_migrations recorder row is written.
        script = Path('/repo/deploy/release/selftest/non_atomic_probe.py')
        result = run(['/opt/test-venv/bin/python', script], env=pg_env)
        print(result.stdout, flush=True)

    # Actual non-atomic Django migration: first SQL commits, second fails; the
    # migration recorder has no row. This is why release failure must be UNKNOWN.
    run(['psql', '-v', 'ON_ERROR_STOP=1', '-c', "ALTER ROLE postgres PASSWORD 'local-only-admin'"], user='postgres')
    env = dict(os.environ, RASTISI_TEST_PG_BIN='/usr/lib/postgresql/16/bin', RASTISI_TEST_PG_ADMIN_URL='postgresql://postgres:local-only-admin@127.0.0.1:5432/postgres', RASTISI_TEST_RESTIC='/usr/bin/restic')
    result = run(['/opt/test-venv/bin/python', '-m', 'unittest', 'discover', '-s', '/repo/deploy/backup/tests', '-p', 'test_*.py', '-v'], env=env)
    print(result.stderr, flush=True)
    exercise_ssh_release(ssh)
    print('PASS isolated installation integration suite', flush=True)


def exercise_ssh_release(ssh):
    """Real SSH transport; fake app/systemctl isolate the service boundary."""
    import signal
    sys.path.insert(0, '/repo/deploy/release/tests')
    from harness import make_artifact
    root = Path('/test')
    fake = root/'fake-service'
    fake.mkdir(mode=0o2775)
    (fake/'flags.json').write_text(json.dumps({'base':'/srv/rastisi-releases'}))
    (fake/'calls.log').touch()
    os.chmod(fake/'calls.log', 0o664)
    run(['chown','-R','rastisi-deploy:rastisi', fake])
    control, db = root/'control.json', root/'db.json'
    control.write_text('{}')
    db.write_text(json.dumps({'rows':['order-canary'], 'applied':[]}))
    run(['chown','rastisi:rastisi',control,db])
    static = root/'static'
    static.mkdir()
    run(['chown','rastisi:rastisi',static])
    with open('/etc/rastisi/test.env','a') as env:
        env.write('DJANGO_DEBUG=False\nDJANGO_SECRET_KEY=local-test-secret-key\nDJANGO_ALLOWED_HOSTS=rastisi.test\nRASTISI_RATE_LIMIT_CACHE_URL=redis://127.0.0.1:6379/0\nDJANGO_STATIC_ROOT=/test/static\nDJANGO_MEDIA_ROOT=/test/media\nSTUB_CONTROL=/test/control.json\nSTUB_DB=/test/db.json\n')
    conf = Path('/etc/rastisi/deploy.conf')
    text = conf.read_text().replace('jobs_follow_current = false','jobs_follow_current = true').replace('edge_probe_enabled = true', 'edge_probe_enabled = false')
    text = text.replace('systemctl = sudo -n /usr/bin/systemctl','systemctl = /usr/bin/python3 /repo/deploy/release/tests/stubs/fake_systemctl.py /test/fake-service')
    text = text.replace('systemctl_show = /usr/bin/systemctl','systemctl_show = /usr/bin/python3 /repo/deploy/release/tests/stubs/fake_systemctl.py /test/fake-service')
    text += '\nprobe_script = /repo/deploy/release/tests/stubs/stub_probe.py\nsmoke_script = /repo/deploy/release/tests/stubs/stub_smoke.py\nproc_root = /test/fake-service/proc\nhealth_timeout = 6\n'
    # Avoid duplicate health_timeout in configparser's strict format.
    text = text.replace('health_timeout = 90','health_timeout = 6').replace('\nhealth_timeout = 6\n','\n',1)
    conf.write_text(text)
    def stage(**kwargs):
        art, sha, digest = make_artifact(root, **kwargs)
        with open(art,'rb') as src:
            result = subprocess.run(ssh+['stage %s %s' % (sha,digest)],stdin=src,capture_output=True,text=True,timeout=120)
        assert result.returncode == 0, result.stdout + result.stderr
        return json.loads(result.stdout.strip().splitlines()[-1])['release'],sha
    def start(rid,sha):
        return run(ssh+['activate %s %s -' % (rid,sha)]).stdout.split()[1]
    def finish(run_id):
        for _ in range(100):
            response = run(ssh+['follow %s 0' % run_id]).stdout
            states = [line for line in response.splitlines() if line.startswith('STATE ')]
            if states and states[-1].startswith('STATE done'):
                return int(states[-1].split()[2])
            time.sleep(0.2)
        raise AssertionError('detached SSH deployment did not finish')
    first,sha = stage()
    assert finish(start(first,sha)) == 0
    control.write_text(json.dumps({'smoke_delay':5}))
    second,sha2 = stage()
    run_id = start(second,sha2)
    # Kill an actual SSH follower. The detached activation continues.
    follower = subprocess.Popen(ssh+['follow %s 0' % run_id],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    follower.kill()
    follower.communicate()
    other,sha3 = stage()
    competing = start(other,sha3)
    assert finish(competing) == 75
    assert finish(run_id) == 0
    control.write_text('{}')
    result = run(ssh+['rollback previous'])
    assert finish(result.stdout.split()[1]) == 0
    assert json.loads(db.read_text())['rows'] == ['order-canary']
    print('PASS real SSH disconnect + concurrent activation rejection + rollback preserves synthetic data (service/app are stubs)',flush=True)


if __name__ == '__main__':
    main()
