#!/usr/bin/env bash
set -euo pipefail
script="$(cd "$(dirname "$0")/.." && pwd)/deploy/openshift/production-backup-rotation.sh"
root=$(mktemp -d)
trap 'rm -rf -- "$root"' EXIT

add_backup() {
  local day=$1 name="backup-${1}T061000-AbCd1234"
  mkdir "$root/$name"
  printf 'fixture %s\n' "$day" > "$root/$name/database.dump"
  (cd "$root/$name" && sha256sum database.dump > SHA256SUMS)
}

# Six weeks of weekdays, with an additional pinned pre-migration point.
for offset in $(seq 0 41); do
  day=$(date -d "2026-12-18 - $offset days" +%Y%m%d)
  weekday=$(date -d "2026-12-18 - $offset days" +%u)
  (( weekday > 5 )) || add_backup "$day"
done
touch "$root/backup-20261109T061000-AbCd1234/KEEP"
BACKUP_ROOT="$root" bash "$script" >/dev/null
test "$(find "$root" -mindepth 1 -maxdepth 1 -type d -name 'backup-*' | wc -l)" -eq 11
for day in 20261214 20261215 20261216 20261217 20261218 20261211 20261204 20261127 20261120 20261113 20261109; do
  test -d "$root/backup-${day}T061000-AbCd1234"
done

# A missing Friday retains the next older Friday rather than an empty slot.
rm -rf "$root/backup-20261211T061000-AbCd1234"
add_backup 20261106
BACKUP_ROOT="$root" bash "$script" >/dev/null
test -d "$root/backup-20261106T061000-AbCd1234"
test "$(find "$root" -mindepth 1 -maxdepth 1 -type d -name 'backup-*' | wc -l)" -eq 11

# An incomplete or corrupt archive must prevent every deletion.
add_backup 20261110
printf 'corruption' >> "$root/backup-20261110T061000-AbCd1234/database.dump"
before=$(find "$root" -mindepth 1 -maxdepth 1 -type d -name 'backup-*' | wc -l)
if BACKUP_ROOT="$root" bash "$script" >/dev/null 2>&1; then
  echo 'Expected corrupt archive to block retention' >&2
  exit 1
fi
test "$before" -eq "$(find "$root" -mindepth 1 -maxdepth 1 -type d -name 'backup-*' | wc -l)"
echo 'Production retention tests passed.'
