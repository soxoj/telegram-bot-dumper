"""Run the webapp server's built-in self-check under pytest.

server.py already asserts its parsing/search/path-safety invariants in selftest();
this just wires that into `pytest tests/`. telethon/dumper are imported lazily
inside server.py, so importing it here needs no token and no network.
"""
import importlib.util
import os

SERVER = os.path.join(os.path.dirname(__file__), '..', 'webapp', 'server.py')


def _load():
    spec = importlib.util.spec_from_file_location('webapp_server', SERVER)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_webapp_selftest():
    _load().selftest()  # asserts inside; raises on any failure
