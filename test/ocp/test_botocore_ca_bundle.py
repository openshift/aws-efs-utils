"""OpenShift bundle adjustment tests; run with pristine botocore 1.34.140."""

import csv
import hashlib
import importlib.metadata
import importlib.util
import ssl
from pathlib import Path

import pytest


HELPER = Path(__file__).resolve().parents[2] / "update-botocore-bundle-ocp.py"


@pytest.fixture
def helper():
    spec = importlib.util.spec_from_file_location("bundle_adjustment", HELPER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def inputs(tmp_path, helper):
    dist = importlib.metadata.distribution("botocore")
    assert dist.version == helper.VERSION
    original = Path(dist.locate_file("botocore/cacert.pem")).read_bytes()
    assert hashlib.sha256(original).hexdigest() == helper.BEFORE
    bundle = tmp_path / "cacert.pem"
    bundle.write_bytes(original)
    record = tmp_path / "RECORD"
    with record.open("w", newline="") as stream:
        csv.writer(stream).writerows([
            ["botocore/cacert.pem", helper.record_hash(original), str(len(original))],
            ["unrelated.py", "sha256=unchanged", "123"],
            ["botocore-1.34.140.dist-info/RECORD", "", ""],
        ])
    return bundle, record


def test_exact_delta_and_repeat_application(helper, inputs):
    bundle, record = inputs
    original = bundle.read_bytes()
    before = helper.certificates(original)
    helper.update(bundle, record, helper.VERSION)
    changed = bundle.read_bytes()
    after = helper.certificates(changed)
    assert hashlib.sha256(changed).hexdigest() == helper.AFTER
    assert len(before) == len(after) + 1
    removed = set(before) - set(after)
    assert after == [cert for cert in before if cert not in removed]
    assert changed == original[:helper.OFFSET] + original[helper.OFFSET + helper.LENGTH:]
    assert len(original.splitlines()) - len(changed.splitlines()) == 33
    with record.open(newline="") as stream:
        rows = list(csv.reader(stream))
    assert rows[0] == ["botocore/cacert.pem", helper.record_hash(changed), str(len(changed))]
    assert rows[1] == ["unrelated.py", "sha256=unchanged", "123"]
    saved = record.read_bytes()
    helper.update(bundle, record, helper.VERSION)
    assert bundle.read_bytes() == changed
    assert record.read_bytes() == saved


@pytest.mark.parametrize("mutation", ["unexpected", "empty", "partial", "malformed", "wrong-certificate"])
def test_unexpected_bundle_fails_closed(helper, inputs, mutation):
    bundle, record = inputs
    original = bundle.read_bytes()
    changes = {
        "unexpected": original + b"\n",
        "empty": b"",
        "partial": original[:helper.OFFSET] + original[helper.OFFSET + 10:],
        "malformed": original.replace(b"BEGIN CERTIFICATE", b"BEGIN INVALID", 1),
        "wrong-certificate": original[:helper.OFFSET] + original[helper.OFFSET:].replace(b"MII", b"NII", 1),
    }
    bundle.write_bytes(changes[mutation])
    saved = record.read_bytes()
    with pytest.raises(ValueError):
        helper.update(bundle, record, helper.VERSION)
    assert bundle.read_bytes() == changes[mutation]
    assert record.read_bytes() == saved


def test_wrong_version_fails_without_changes(helper, inputs):
    bundle, record = inputs
    saved = bundle.read_bytes(), record.read_bytes()
    with pytest.raises(ValueError):
        helper.update(bundle, record, "1.43.117")
    assert (bundle.read_bytes(), record.read_bytes()) == saved


def test_missing_bundle_fails(helper, inputs):
    bundle, record = inputs
    bundle.unlink()
    with pytest.raises(FileNotFoundError):
        helper.update(bundle, record, helper.VERSION)


@pytest.mark.parametrize("record_text", ["", "botocore/cacert.pem,sha256=wrong,1\n", "other.pem,,\n"])
def test_invalid_record_fails_before_mutation(helper, inputs, record_text):
    bundle, record = inputs
    original = bundle.read_bytes()
    record.write_text(record_text)
    with pytest.raises(ValueError):
        helper.update(bundle, record, helper.VERSION)
    assert bundle.read_bytes() == original


def test_malformed_certificate_parser_rejects(helper):
    with pytest.raises((ValueError, ssl.SSLError)):
        helper.certificates(b"-----BEGIN CERTIFICATE-----\nnot-valid\n-----END CERTIFICATE-----\n")
