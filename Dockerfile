FROM registry.ci.openshift.org/ocp/4.20:base-rhel9

# install deps
RUN yum update -y && \
    yum install --setopt=tsflags=nodocs -y nfs-utils stunnel python3 openssl util-linux which && \
    yum clean all && rm -rf /var/cache/yum/*

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
