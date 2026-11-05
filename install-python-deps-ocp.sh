#!/usr/bin/bash

# Install all efs-utils deps. Prefer RPMs, but in the end install the
# remaining ones (= botocore) using pip.
# Make sure pip installs from a local cache in the Red Hat build pipeline.
# Everywhere else, let pip install from the internet.

set -euxo pipefail

yum update -y
yum install --setopt=tsflags=nodocs -y nfs-utils stunnel python3 openssl util-linux which make python3-pip python3-jmespath python3-urllib3 python3-six.noarch python3-wheel python3-dateutil patch
yum clean all
rm -rf /var/cache/yum/*

SRC=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REQS="${SRC}/requirements.txt.ocp"

if [[ -v REMOTE_SOURCES ]]; then
    echo "Red Hat build pipeline detected"
    ls -lR "${REMOTE_SOURCES_DIR}/" # DEBUG

    # Load cachito variables and requirements.txt.
    # This re-configures pip to use the build system cache.
    if [[ -d "${REMOTE_SOURCES_DIR}/cachito-gomod-with-deps" ]]; then
        source "${REMOTE_SOURCES_DIR}/cachito-gomod-with-deps/cachito.env"
        REQS="${REMOTE_SOURCES_DIR}/cachito-gomod-with-deps/app/requirements.txt.ocp"
    fi
fi

# Prepare the pinned botocore wheel using the same pip source/cache configuration.
# --no-build-isolation: use setuptools and wheel from RPM packages.
# Patch before installation; wheel pack regenerates RECORD for the edited files.
WORK=$(mktemp -d "${TMPDIR:-/tmp}/botocore-wheel-XXXXXX")
trap 'rm -rf -- "${WORK}"' EXIT
mkdir -p "${WORK}/input" "${WORK}/output"
PACKAGE=botocore-1.34.140
WHEEL="${PACKAGE}-py3-none-any.whl"

python3 -m pip wheel --no-deps --no-build-isolation -r "${REQS}" -w "${WORK}/input"
python3 -m wheel unpack "${WORK}/input/${WHEEL}" -d "${WORK}/unpacked"
BUNDLE="${WORK}/unpacked/${PACKAGE}/botocore/cacert.pem"
printf '%s  %s\n' \
    9d6d5021fcc8a2232fce8eb4b3f982dc484252d555493ac5c2a3cbf2cb19438a "${BUNDLE}" | sha256sum --check
patch --batch --forward --fuzz=0 -p1 -d "${WORK}/unpacked/${PACKAGE}" -i "${SRC}/botocore-ca-bundle.patch"
printf '%s  %s\n' \
    76822f65ad3bbc0285d1a656063f9828154c1d736ebbcb339909337277910dfa "${BUNDLE}" | sha256sum --check
python3 -m wheel pack "${WORK}/unpacked/${PACKAGE}" -d "${WORK}/output"

# Resolve dependencies normally, preferring the RPMs installed above.
python3 -m pip install --no-build-isolation "${WORK}/output/${WHEEL}"
