# Dockefile for OpenShift base image named "aws-efs-utils-base"
#
# The image contains:
# - /sbin/mount.efs
# - /usr/bin/amazon-efs-mount-watchdog
# - /etc/amazon/*
# - /var/log/amazon/efs/*
# - botocore3 (to be able to use zonal EFS volumes)

FROM registry.ci.openshift.org/ocp/4.21:base-rhel9

# create log file
RUN mkdir -p /var/log/amazon/efs
RUN touch /var/log/amazon/efs/mount.log

# certs
COPY ./dist/efs-utils.crt /etc/amazon/efs/efs-utils.crt
RUN chmod 644 /etc/amazon/efs/efs-utils.crt
COPY ./dist/efs-utils.conf /etc/amazon/efs/efs-utils.conf
RUN chmod 444 /etc/amazon/efs/efs-utils.conf
COPY ./src/mount_efs/__init__.py /sbin/mount.efs
RUN chmod 755 /sbin/mount.efs
COPY ./src/watchdog/__init__.py /usr/bin/amazon-efs-mount-watchdog
RUN chmod 755 /usr/bin/amazon-efs-mount-watchdog

# Copy cachito / hermeto files used in the build pipeline. Copy an innocent file if the env. vars are not set.
ENV REMOTE_SOURCES_SRC=${REMOTE_SOURCES:-"requirements.txt"}
ENV REMOTE_SOURCES_DST=${REMOTE_SOURCES_DIR:-"/remote_sources_dir/"}
COPY "$REMOTE_SOURCES_SRC" "$REMOTE_SOURCES_DST"

# Install python dependencies (i.e. botocore).
COPY requirements.txt.ocp install-python-deps-ocp.sh /src/
RUN /src/install-python-deps-ocp.sh
