#!/bin/bash -e
install -d "${ROOTFS_DIR}/opt/aerosignal"
tar --exclude=.git --exclude=.preview --exclude=dist -C "${BASE_DIR}/aerosignal-source" -cf - . | tar -C "${ROOTFS_DIR}/opt/aerosignal" -xf -
