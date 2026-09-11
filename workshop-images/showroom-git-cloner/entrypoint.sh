#!/bin/bash

set -euo pipefail

export GIT_TERMINAL_PROMPT=0
export GIT_CONFIG_GLOBAL=/tmp/.gitconfig

: "${GIT_REPO_URL:?Error: GIT_REPO_URL environment variable is not set or empty.}"

CLONE_DIR="${CLONE_DIR:-/files}"
GIT_REPO_REF="${GIT_REPO_REF:-}"

if [[ -d "${CLONE_DIR}" ]]; then
    rm -f "${CLONE_DIR}/.git-cloner"
    find "${CLONE_DIR}" -mindepth 1 -delete
fi

echo "Cloning ${GIT_REPO_URL} into ${CLONE_DIR}"

# The emptyDir can be owned by a supplemental OpenShift group rather than the
# container UID. Trust the destination before any repository-aware command,
# including init and fetch for an immutable commit SHA.
git config --global --add safe.directory "${CLONE_DIR}"

clone_args=(clone --progress --depth 1)
checkout_sha=false
if [[ -n "${GIT_REPO_REF}" ]]; then
    if [[ "${GIT_REPO_REF}" =~ ^[0-9a-fA-F]{7,40}$ ]]; then
        checkout_sha=true
    else
        clone_args+=(--single-branch --branch "${GIT_REPO_REF}")
    fi
else
    clone_args+=(--single-branch)
fi
clone_success=false
if [[ "${checkout_sha}" == true ]]; then
    mkdir -p "${CLONE_DIR}"
    git -C "${CLONE_DIR}" init
    git -C "${CLONE_DIR}" remote add origin "${GIT_REPO_URL}"
    for attempt in {1..10}; do
        if git -C "${CLONE_DIR}" fetch --depth 1 origin "${GIT_REPO_REF}"; then
            git -C "${CLONE_DIR}" checkout --detach FETCH_HEAD
            clone_success=true
            break
        fi
        echo "Fetch attempt ${attempt} failed; retrying in 10 seconds"
        sleep 10
    done
else
    clone_args+=("${GIT_REPO_URL}" "${CLONE_DIR}")
    for attempt in {1..10}; do
        if git "${clone_args[@]}"; then
            clone_success=true
            break
        fi
        echo "Clone attempt ${attempt} failed; retrying in 10 seconds"
        sleep 10
    done
fi
[[ "${clone_success}" == true ]] || exit 1

cd "${CLONE_DIR}"
touch .git-cloner

echo "Repository clone completed"
