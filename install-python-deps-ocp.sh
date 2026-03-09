#!/usr/bin/bash

# Install all efs-utils deps. Prefer RPMs, but in the end install the
# remaining ones (= botocore) using pip.
# Make sure pip installs from a local cache in the Red Hat build pipeline.
# Everywhere else, let pip install from the internet.

set -euxo pipefail

yum update -y
yum install --setopt=tsflags=nodocs -y nfs-utils stunnel python3 openssl util-linux which make python3-pip python3-jmespath python3-urllib3 python3-attrs python3-py python3-tomli python3-iniconfig python3-six.noarch python3-wheel python3-dateutil
yum clean all
rm -rf /var/cache/yum/*

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
