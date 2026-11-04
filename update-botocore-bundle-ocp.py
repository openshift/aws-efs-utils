#!/usr/bin/python3
"""Apply the OpenShift build-time bundle adjustment to the pinned dependency.

Only the complete known input or complete known output is accepted. The package
version is unchanged; bundle hashes and this build input record the local delta.
"""

import base64
import csv
import hashlib
import importlib.metadata
import io
import os
from pathlib import Path
import re
import ssl
import tempfile


VERSION = "1.34.140"
BEFORE = "9d6d5021fcc8a2232fce8eb4b3f982dc484252d555493ac5c2a3cbf2cb19438a"
AFTER = "76822f65ad3bbc0285d1a656063f9828154c1d736ebbcb339909337277910dfa"
OFFSET = 22055
LENGTH = 1948


def record_hash(data):
    digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest())
    return "sha256=" + digest.rstrip(b"=").decode("ascii")


def certificates(data):
    blocks = re.findall(
        rb"-----BEGIN CERTIFICATE-----\n.*?-----END CERTIFICATE-----\n",
        data,
        re.DOTALL,
    )
    if not blocks:
        raise ValueError("No certificates in dependency bundle")
    for block in blocks:
        ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT).load_verify_locations(
            cadata=block.decode("ascii")
        )
    return blocks


def atomic_write(path, data):
    fd, name = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            os.fchmod(stream.fileno(), path.stat().st_mode & 0o777)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def update(bundle, record, version):
    if version != VERSION:
        raise ValueError("Unexpected botocore version: " + version)
    original = bundle.read_bytes()
    digest = hashlib.sha256(original).hexdigest()
    if digest not in (BEFORE, AFTER):
        raise ValueError("Unexpected dependency bundle SHA-256: " + digest)
    rows = list(csv.reader(io.StringIO(record.read_text())))
    matches = [row for row in rows if row and row[0] == "botocore/cacert.pem"]
    if len(matches) != 1 or matches[0][1:] != [record_hash(original), str(len(original))]:
        raise ValueError("Missing or inconsistent bundle entry in wheel RECORD")
    before = certificates(original)
    if digest == AFTER:
        return
    changed = original[:OFFSET] + original[OFFSET + LENGTH:]
    if hashlib.sha256(changed).hexdigest() != AFTER:
        raise ValueError("Unexpected adjusted dependency bundle")
    after = certificates(changed)
    removed = set(before) - set(after)
    if len(removed) != 1 or [cert for cert in before if cert not in removed] != after:
        raise ValueError("Unexpected certificate delta")
    matches[0][1:] = [record_hash(changed), str(len(changed))]
    output = io.StringIO(newline="")
    csv.writer(output).writerows(rows)
    # Both inputs are validated before either write. Any failed write aborts the
    # image build; a mixed bundle/RECORD state is never accepted on a later run.
    atomic_write(bundle, changed)
    atomic_write(record, output.getvalue().encode("utf-8"))


def main():
    dist = importlib.metadata.distribution("botocore")
    records = [p for p in dist.files or []
               if p.name == "RECORD" and p.parent.name.endswith(".dist-info")]
    if len(records) != 1:
        raise ValueError("Expected one installed wheel RECORD")
    bundle = Path(dist.locate_file("botocore/cacert.pem"))
    update(bundle, Path(dist.locate_file(records[0])), dist.version)
    print("OpenShift botocore bundle adjustment:", dist.version, BEFORE, "->", AFTER)


if __name__ == "__main__":
    main()
