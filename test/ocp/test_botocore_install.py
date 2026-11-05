"""Exercise the real wheel preparation offline; stub only RPM/host operations.

Requires pristine botocore 1.34.140 and wheel in the test environment.
"""

import base64
import csv
import difflib
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import shutil
import ssl
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
PACKAGE = "botocore-1.34.140"
BEFORE = "9d6d5021fcc8a2232fce8eb4b3f982dc484252d555493ac5c2a3cbf2cb19438a"
AFTER = "76822f65ad3bbc0285d1a656063f9828154c1d736ebbcb339909337277910dfa"


@pytest.fixture(scope="module")
def wheel_source(tmp_path_factory):
    root = tmp_path_factory.mktemp("botocore-input")
    source = root / PACKAGE
    source.mkdir()
    dist = importlib.metadata.distribution("botocore")
    assert dist.version == "1.34.140"
    shutil.copytree(dist.locate_file("botocore"), source / "botocore",
                    ignore=shutil.ignore_patterns("__pycache__"))
    metadata = source / (PACKAGE + ".dist-info")
    metadata.mkdir()
    for name in ("METADATA", "WHEEL"):
        (metadata / name).write_text(dist.read_text(name))
    original = (source / "botocore/cacert.pem").read_bytes()
    assert hashlib.sha256(original).hexdigest() == BEFORE
    return source


@pytest.fixture
def installation(tmp_path, wheel_source):
    src = tmp_path / "src"
    src.mkdir()
    shutil.copy(ROOT / "install-python-deps-ocp.sh", src)
    shutil.copy(ROOT / "requirements.txt.ocp", src)
    patch = ROOT / "botocore-ca-bundle.patch"
    if patch.exists():
        shutil.copy(patch, src)
    cache = tmp_path / "cache"
    cache.mkdir()
    tools = tmp_path / "bin"
    tools.mkdir()
    # Never run yum or remove the host yum cache.
    for name in ("yum", "rm"):
        tool = tools / name
        tool.write_text("#!/bin/bash\n"
                        "if [[ $0 == */rm && $* != *'/var/cache/yum/'* ]]; then\n"
                        "    exec /bin/rm \"$@\"\n"
                        "fi\nexit 0\n")
        tool.chmod(0o755)
    python = tools / "python3"
    python.write_text(
        "#!" + sys.executable + "\n"
        "import json, os, sys\n"
        "args = sys.argv[1:]\n"
        "with open(os.environ['COMMAND_LOG'], 'a') as stream:\n"
        "    stream.write(json.dumps([args, os.environ.get('CACHE_ROUTE')]) + '\\n')\n"
        "stage = args[2] if args[:2] in (['-m', 'pip'], ['-m', 'wheel']) else 'helper'\n"
        "if stage == os.environ.get('FAIL_STAGE'):\n"
        "    sys.exit(23)\n"
        "if args[:3] == ['-m', 'pip', 'install']:\n"
        "    args += ['--target', os.environ['INSTALL_TARGET'], '--no-deps']\n"
        "os.execv(sys.executable, [sys.executable] + args)\n"
    )
    python.chmod(0o755)
    work = tmp_path / "work"
    work.mkdir()
    env = os.environ.copy()
    for key in ("REMOTE_SOURCES", "REMOTE_SOURCES_DIR", "FAIL_STAGE", "CACHE_ROUTE"):
        env.pop(key, None)
    env.update(PATH=str(tools) + os.pathsep + os.defpath,
               COMMAND_LOG=str(tmp_path / "commands.jsonl"),
               INSTALL_TARGET=str(tmp_path / "installed"),
               PIP_NO_INDEX="1", PIP_FIND_LINKS=str(cache),
               PIP_DISABLE_PIP_VERSION_CHECK="1", TMPDIR=str(work))
    return src, cache, tools, work, env


def run_installer(installation, wheel_source):
    src, cache, tools, work, env = installation
    subprocess.run([sys.executable, "-m", "wheel", "pack", str(wheel_source),
                    "--dest-dir", str(cache)], check=True, capture_output=True)
    result = subprocess.run(["bash", str(src / "install-python-deps-ocp.sh")],
                            env=env, capture_output=True, text=True)
    log = Path(env["COMMAND_LOG"])
    commands = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
    return result, commands


@pytest.mark.parametrize("route", ["normal", "cached", "cache-missing"])
def test_real_wheel_pipeline(installation, wheel_source, route):
    src, cache, tools, work, env = installation
    requirements = src / "requirements.txt.ocp"
    if route != "normal":
        remote = src.parent / "remote"
        remote.mkdir()
        env.update(REMOTE_SOURCES="present", REMOTE_SOURCES_DIR=str(remote))
        if route == "cached":
            collected = remote / "cachito-gomod-with-deps"
            (collected / "app").mkdir(parents=True)
            (collected / "cachito.env").write_text("export CACHE_ROUTE=collected\nexport PIP_NO_INDEX=1\n")
            requirements = collected / "app/requirements.txt.ocp"
            requirements.write_text("botocore==1.34.140\n")
    result, commands = run_installer(installation, wheel_source)
    assert result.returncode == 0, result.stdout + result.stderr
    stages = [command[0][:3] for command in commands]
    assert stages == [["-m", "pip", "wheel"], ["-m", "wheel", "unpack"],
                      ["-m", "wheel", "pack"], ["-m", "pip", "install"]]
    args = commands[0][0]
    assert args[args.index("-r") + 1] == str(requirements)
    assert "--no-build-isolation" in args and "--no-deps" in args
    assert all(command[1] == ("collected" if route == "cached" else None) for command in commands)
    assert "--ignore-requires-python" not in str(commands)
    assert "--no-deps" not in commands[-1][0]
    installed = Path(env["INSTALL_TARGET"])
    bundle = (installed / "botocore/cacert.pem").read_bytes()
    assert hashlib.sha256(bundle).hexdigest() == AFTER
    original = (wheel_source / "botocore/cacert.pem").read_bytes()
    pattern = rb"-----BEGIN CERTIFICATE-----\n.*?-----END CERTIFICATE-----\n"
    before = re.findall(pattern, original, re.DOTALL)
    after = re.findall(pattern, bundle, re.DOTALL)
    removed = set(before) - set(after)
    assert len(removed) == 1
    assert after == [cert for cert in before if cert not in removed]
    assert len(original.splitlines()) - len(bundle.splitlines()) == 33
    ssl.create_default_context(cadata=bundle.decode("ascii"))
    with (installed / (PACKAGE + ".dist-info/RECORD")).open(newline="") as stream:
        rows = list(csv.reader(stream))
    entry = next(row for row in rows if row[0] == "botocore/cacert.pem")
    digest = base64.urlsafe_b64encode(hashlib.sha256(bundle).digest()).rstrip(b"=").decode("ascii")
    assert entry == ["botocore/cacert.pem", "sha256=" + digest, str(len(bundle))]
    assert (installed / "botocore/session.py").read_bytes() == (wheel_source / "botocore/session.py").read_bytes()
    assert not list(work.iterdir()), "temporary build files must be cleaned"


@pytest.mark.parametrize("stage", ["wheel", "unpack", "pack", "install", "patch"])
def test_failed_stage_aborts_and_cleans(installation, wheel_source, stage):
    src, cache, tools, work, env = installation
    if stage == "patch":
        executable = tools / "patch"
        executable.write_text("#!/bin/sh\nexit 23\n")
        executable.chmod(0o755)
    else:
        env["FAIL_STAGE"] = stage
    result, commands = run_installer(installation, wheel_source)
    assert result.returncode == 23, result.stdout + result.stderr
    assert not Path(env["INSTALL_TARGET"]).exists()
    assert not list(work.iterdir())
    if stage != "install":
        assert all(command[0][:3] != ["-m", "pip", "install"] for command in commands)


@pytest.mark.parametrize("mutation", ["input", "output", "missing-patch", "python-version"])
def test_invalid_input_never_installed(installation, wheel_source, tmp_path, mutation):
    src, cache, tools, work, env = installation
    source = wheel_source
    if mutation in ("input", "python-version"):
        source = tmp_path / PACKAGE
        shutil.copytree(wheel_source, source)
        if mutation == "input":
            with (source / "botocore/cacert.pem").open("ab") as stream:
                stream.write(b"\n")
        else:
            metadata = source / (PACKAGE + ".dist-info/METADATA")
            original = metadata.read_text()
            changed = re.sub(r"(?m)^Requires-Python:.*$", "Requires-Python: >=3.10", original)
            assert changed != original
            metadata.write_text(changed)
    elif mutation == "output":
        original = (wheel_source / "botocore/cacert.pem").read_text()
        changed = original.replace("# Issuer:", "# Changed:", 1)
        (src / "botocore-ca-bundle.patch").write_text("".join(difflib.unified_diff(
            original.splitlines(True), changed.splitlines(True),
            fromfile="a/botocore/cacert.pem", tofile="b/botocore/cacert.pem")))
    else:
        (src / "botocore-ca-bundle.patch").unlink(missing_ok=True)
    result, commands = run_installer(installation, source)
    assert result.returncode != 0
    assert all(command[0][:3] != ["-m", "pip", "install"] for command in commands)
    assert not Path(env["INSTALL_TARGET"]).exists()
    assert not list(work.iterdir())
