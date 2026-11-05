#!/usr/bin/bash

# Install all efs-utils deps. Prefer RPMs, but in the end install the
# remaining ones (= botocore) using pip.
# Make sure pip installs from a local cache in the Red Hat build pipeline.
# Everywhere else, let pip install from the internet.

set -euxo pipefail

yum update -y
yum install --setopt=tsflags=nodocs -y nfs-utils stunnel openssl util-linux which make python3.12 python3.12-pip python3.12-setuptools python3.12-wheel
yum clean all
rm -rf /var/cache/yum/*

# Configure python3 to use python3.12 since RHEL 9 defaults to python3.9
ln -sf /usr/bin/python3.12 /usr/bin/python3
ln -sf /usr/bin/pip3.12 /usr/bin/pip3
ln -sf /usr/bin/pip3.12 /usr/bin/pip

REQS=/src/requirements.txt.ocp

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

# Finally, install all remaining requirements, ideally just botocore.
# --no-build-isolation: use system setuptools and /bin/wheel from RPM packages.
python3 -m pip install -r "${REQS}" --no-build-isolation
