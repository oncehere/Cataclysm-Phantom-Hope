#!/usr/bin/env bash
# Adapted from Ethan Kemp's mp-stack.sh at MP upstream 5cf9a79c66ec.
# Inspect one explicitly selected CPH process; never select another game's PID.
set -euo pipefail

usage() {
    printf 'Usage: %s PID [macOS-sample-seconds]\n' "$0"
    printf 'Linux: one gdb stack snapshot. macOS: sample (default 2 seconds).\n'
}

if [[ ${1:-} == --help || ${1:-} == -h ]]; then
    usage
    exit 0
fi
if [[ $# -lt 1 || $# -gt 2 || ! ${1:-} =~ ^[1-9][0-9]*$ ]]; then
    usage >&2
    exit 2
fi
mp_pid=$1
mp_seconds=${2:-2}
if [[ ! $mp_seconds =~ ^[1-9][0-9]*$ || ${#mp_seconds} -gt 2 || $mp_seconds -gt 30 ]]; then
    printf 'Sample duration must be between 1 and 30 seconds.\n' >&2
    exit 2
fi
if ! kill -0 "$mp_pid" 2>/dev/null; then
    printf 'PID %s is unavailable.\n' "$mp_pid" >&2
    exit 1
fi

case $(uname -s) in
    Darwin)
        command -v sample >/dev/null || { printf 'macOS sample is required.\n' >&2; exit 1; }
        mp_output=$(mktemp "${TMPDIR:-/tmp}/cph-mp-stack.XXXXXX")
        trap 'rm -f "$mp_output"' EXIT
        sample "$mp_pid" "$mp_seconds" -f "$mp_output" >/dev/null
        # Retain the native call graph, including CPH, SDL and system frames.
        # Keeping all names also supports custom CPH binary names.
        sed -n '/Call graph:/,$p' "$mp_output"
        ;;
    Linux)
        command -v gdb >/dev/null || { printf 'gdb is required for the Linux snapshot.\n' >&2; exit 1; }
        # gdb briefly stops the selected process and detaches after the snapshot.
        # Debug symbols are needed for source file and line information.
        exec gdb -nx -nh -batch -p "$mp_pid" \
            -ex 'set pagination off' -ex 'thread apply all bt 30' -ex detach
        ;;
    *)
        printf 'This helper supports Linux and macOS.\n' >&2
        exit 1
        ;;
esac
