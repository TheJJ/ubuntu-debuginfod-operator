#!/bin/bash

# Common definitions
readonly DIR=/srv/debug-mirror
readonly RSYNC=/usr/bin/rsync

# Only execute if ${DIR} is mounted.
if ! mountpoint -q "${DIR}"; then
        echo "E: ${DIR} is not mounted; aborting." > /dev/stderr
        exit 1
fi

if [ ! -t ]; then
        readonly RSYNC_OPTS="-azm --size-only --quiet"
else
        readonly RSYNC_OPTS="-avzm --size-only --progress"
fi

# Sync from ddebs.internal
sync_ddebs()
{
        local -r DDEBS_HOST="ddebs.internal"
        local -r DDEBS_REMOTE_DIR="ddebs/pool/"
        local -r DDEBS_LOCAL_DIR="${DIR}/ddebs"

        # Copy from ddebs
        ${RSYNC} ${RSYNC_OPTS} --dry-run --include='*/' --include='*.ddeb' --exclude='*' ${DDEBS_HOST}::${DDEBS_REMOTE_DIR} ${DDEBS_LOCAL_DIR}
}

# Sync from *.rsync.archive.ubuntu.com
sync_ubuntu_archive()
{
        # Copy from regular archive
        local -r UBUNTU_ARCHIVE_HOST="gb.rsync.archive.ubuntu.com"
        local -r UBUNTU_ARCHIVE_REMOTE_DIR="ubuntu/pool/"
        local -r UBUNTU_ARCHIVE_LOCAL_DIR="${DIR}/ubuntu-archive-dbg"

        ${RSYNC} ${RSYNC_OPTS} --include='*/' --include='*-dbg*.deb' --exclude='*' ${UBUNTU_ARCHIVE_HOST}::${UBUNTU_ARCHIVE_REMOTE_DIR} ${UBUNTU_ARCHIVE_LOCAL_DIR}
}

#sync_ddebs
sync_ubuntu_archive
