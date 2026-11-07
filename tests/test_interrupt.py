"""Ctrl+C during a dump ends with one line and exit code 130, not a traceback."""
import asyncio
import runpy

import pytest

import dumper


def run_interrupted(monkeypatch, *flags):
    def interrupt(coro):
        coro.close()
        raise KeyboardInterrupt

    monkeypatch.setattr("sys.argv", ["dumper.py", "--token", "1:fake", *flags])
    monkeypatch.setattr(asyncio, "run", interrupt)
    with pytest.raises(SystemExit) as exit_info:
        runpy.run_path(dumper.__file__, run_name="__main__")
    return exit_info.value.code


@pytest.mark.parametrize("flags", [("--down",), ("--resume",), ("--start-from-id", "10")])
def test_downward_dump_hints_at_resume(monkeypatch, capsys, flags):
    assert run_interrupted(monkeypatch, *flags) == 130
    assert capsys.readouterr().out == "Interrupted. History so far is saved; continue with --resume.\n"


@pytest.mark.parametrize("flags", [(), ("--listen-only",), ("--listen-only", "--down")])
def test_other_dumps_omit_the_resume_hint(monkeypatch, capsys, flags):
    assert run_interrupted(monkeypatch, *flags) == 130
    assert capsys.readouterr().out == "Interrupted. History so far is saved.\n"
