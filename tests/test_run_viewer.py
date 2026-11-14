"""run-viewer.sh loads .env next to it and starts the viewer with --allow-new-dumps."""
import os
import shutil
import subprocess
import sys

import pytest

REPO = os.path.join(os.path.dirname(__file__), '..')
pytestmark = pytest.mark.skipif(sys.platform == 'win32' or not shutil.which('sh'), reason='needs a POSIX shell')


def run(tmp_path, env_file=None):
    shutil.copy(os.path.join(REPO, 'run-viewer.sh'), tmp_path)
    os.symlink(os.path.abspath(os.path.join(REPO, 'webapp')), tmp_path / 'webapp')
    if env_file is not None:
        (tmp_path / '.env').write_text(env_file)
    env = {k: v for k, v in os.environ.items() if k not in ('API_ID', 'API_HASH', 'HOST', 'ALLOW_PUBLIC')}
    return subprocess.run(['sh', str(tmp_path / 'run-viewer.sh'), str(tmp_path)],
                          env=env, capture_output=True, text=True, timeout=30)


def test_refuses_without_credentials(tmp_path):
    r = run(tmp_path, 'API_ID=\nAPI_HASH=\n')
    assert r.returncode == 1 and 'cp .env.example .env' in r.stderr


def test_passes_env_and_allow_new_dumps_to_the_server(tmp_path):
    # a public HOST from .env makes the server refuse to start, which proves it got
    # both the .env values and --allow-new-dumps without leaving a server running
    r = run(tmp_path, 'API_ID=1\nAPI_HASH=x\nHOST=0.0.0.0\nPORT=0\n')
    assert r.returncode != 0 and '--allow-public' in r.stderr
