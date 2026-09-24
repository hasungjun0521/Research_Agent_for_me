"""Exercise real executable argument transport using native runner parsing."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys

import pytest

from scripts.harness.runner_commands import split_runner_command


def test_legacy_runner_can_execute_python_with_literal_arguments():
    arguments = ["space separated", "", "a" + chr(92) + "b", 'quote"inside', "??"]
    argv = [sys.executable, "-c", "import sys,json; print(json.dumps(sys.argv[1:]))", *arguments]
    command = subprocess.list2cmdline(argv) if os.name == "nt" else shlex.join(argv)
    parsed = split_runner_command(command)
    assert parsed == argv
    result = subprocess.run(parsed, check=True, capture_output=True, text=True)
    assert json.loads(result.stdout) == arguments


def test_empty_runner_command_is_not_current_executable():
    assert split_runner_command("   ") == []


@pytest.mark.skipif(os.name != "nt", reason="native Windows command line rules")
def test_windows_unquoted_executable_backslashes_are_preserved():
    executable = "C:" + chr(92) + chr(92).join(("Python", "python.exe"))
    assert split_runner_command(executable + ' -c "print(123)"') == [
        executable, "-c", "print(123)",
    ]
