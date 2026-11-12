"""Validate the actual selected interpreter before creating or reusing a venv."""
import json
import subprocess


def check_runtime(python, manifest):
    query = "import json,platform,sys;print(json.dumps({'python':'%d.%d'%sys.version_info[:2],'machine':platform.machine(),'system':platform.system()}))"
    try:
        proc = subprocess.run([python, '-I', '-c', query], capture_output=True, text=True, timeout=30, check=True)
        have = json.loads(proc.stdout)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        raise ValueError('could not inspect selected Python interpreter') from exc
    if not manifest.get('python') or have['python'] != manifest['python']:
        raise ValueError('Python mismatch: artifact %s, selected interpreter %s' % (manifest.get('python'), have['python']))
    # Wheelhouse currently supports only Linux x86_64. pip additionally checks
    # wheel ABI/manylinux tags during the offline hashed installation.
    if have['system'] != 'Linux' or have['machine'] != 'x86_64':
        raise ValueError('unsupported artifact architecture: Linux x86_64 required')
    if manifest.get('platform', 'linux_x86_64') != 'linux_x86_64':
        raise ValueError('artifact platform does not match this builder')
    return have
