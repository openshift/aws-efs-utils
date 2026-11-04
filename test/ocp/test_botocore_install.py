"""Exercise installer routing without network, RPM or host filesystem writes."""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


INSTALLER = Path(__file__).resolve().parents[2] / "install-python-deps-ocp.sh"


@pytest.mark.parametrize("cached", [False, True])
@pytest.mark.parametrize("pip_failure", [False, True])
def test_installation_precedes_adjustment(tmp_path, cached, pip_failure):
    tools = tmp_path / "bin"
    tools.mkdir()
    log = tmp_path / "commands.jsonl"
    for name in ("yum", "rm", "ls"):
        executable = tools / name
        executable.write_text("#!/bin/sh\nexit 0\n")
        executable.chmod(0o755)
    python = tools / "python3"
    python.write_text(
        "#!" + sys.executable + "\n"
        "import json, os, sys\n"
        "with open(os.environ['COMMAND_LOG'], 'a') as stream:\n"
        "    stream.write(json.dumps([sys.argv[1:], os.environ.get('PIP_NO_INDEX')]) + '\\n')\n"
        "if sys.argv[1:4] == ['-m', 'pip', 'install']:\n"
        "    sys.exit(int(os.environ['PIP_FAILURE']))\n"
    )
    python.chmod(0o755)
    env = os.environ.copy()
    env.pop("REMOTE_SOURCES", None)
    env.pop("REMOTE_SOURCES_DIR", None)
    env.pop("PIP_NO_INDEX", None)
    env.update(PATH=str(tools) + os.pathsep + os.defpath,
               COMMAND_LOG=str(log), PIP_FAILURE="23" if pip_failure else "0")
    requirements = "/src/requirements.txt.ocp"
    if cached:
        cache = tmp_path / "remote" / "cachito-gomod-with-deps"
        (cache / "app").mkdir(parents=True)
        (cache / "cachito.env").write_text("export PIP_NO_INDEX=1\n")
        requirements = str(cache / "app" / "requirements.txt.ocp")
        Path(requirements).write_text("botocore==1.34.140\n")
        env.update(REMOTE_SOURCES="present", REMOTE_SOURCES_DIR=str(cache.parent))
    result = subprocess.run(["bash", str(INSTALLER)], env=env, capture_output=True, text=True)
    assert result.returncode == (23 if pip_failure else 0), result.stderr
    commands = [json.loads(line) for line in log.read_text().splitlines()]
    assert commands[0] == [
        ["-m", "pip", "install", "-r", requirements, "--no-build-isolation"],
        "1" if cached else None,
    ]
    if pip_failure:
        assert len(commands) == 1
    else:
        assert commands[1] == [["/src/update-botocore-bundle-ocp.py"], "1" if cached else None]
        assert len(commands) == 2
