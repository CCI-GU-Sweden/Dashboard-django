#!/usr/bin/env bash
# Called only after a successful, published production backup. All archives are
# checked before any deletion; KEEP pins an archive until an operator removes it.
set -euo pipefail
root=${BACKUP_ROOT:?Set BACKUP_ROOT to the dedicated backup directory}
test -d "$root"
lock="$root/.rotation-lock"
if ! mkdir "$lock"; then
  echo 'Retention lock exists; no backups were deleted.' >&2
  exit 1
fi
trap 'rmdir -- "$lock"' EXIT

declare -a archives=()
while IFS= read -r name; do
  [[ -n "$name" ]] && archives+=("$name")
done < <(find "$root" -mindepth 1 -maxdepth 1 -type d -name 'backup-*' -printf '%f\n' | LC_ALL=C sort -r)

declare -A keep=() daily_dates=() weekly_dates=()
for name in "${archives[@]}"; do
  if [[ ! "$name" =~ ^backup-([0-9]{8})T[0-9]{6}-[A-Za-z0-9]+$ ]]; then
    echo "Unexpected backup directory: $name; no backups were deleted." >&2
    exit 1
  fi
  dir="$root/$name"
  if [[ ! -f "$dir/database.dump" || ! -s "$dir/database.dump" || ! -f "$dir/SHA256SUMS" ]]; then
    echo "Incomplete archive: $name; no backups were deleted." >&2
    exit 1
  fi
  # Accept only our own simple manifest, avoiding paths supplied by a manifest.
  digest=$(sha256sum "$dir/database.dump")
  checksum=${digest%% *}
  manifest=$(cat "$dir/SHA256SUMS")
  if [[ "$manifest" != "$checksum  database.dump" && "$manifest" != "$checksum *database.dump" ]]; then
    echo "Checksum mismatch: $name; no backups were deleted." >&2
    exit 1
  fi
  if [[ -e "$dir/KEEP" || "$name" == "${PINNED_BACKUP:-}" ]]; then
    keep["$name"]=1
  fi
done

# Newest successful snapshot on each of the five latest weekdays.
count=0
for name in "${archives[@]}"; do
  day=${name:7:8}
  weekday=$(date -d "${day:0:4}-${day:4:2}-${day:6:2}" +%u)
  if (( weekday <= 5 && count < 5 )) && [[ ! ${daily_dates[$day]+yes} ]]; then
    keep["$name"]=1
    daily_dates["$day"]=1
    ((count+=1))
  fi
done

# Five earlier Fridays, with no duplication of the daily snapshots.
count=0
for name in "${archives[@]}"; do
  day=${name:7:8}
  weekday=$(date -d "${day:0:4}-${day:4:2}-${day:6:2}" +%u)
  if (( weekday == 5 && count < 5 )) && [[ ! ${daily_dates[$day]+yes} && ! ${weekly_dates[$day]+yes} ]]; then
    keep["$name"]=1
    weekly_dates["$day"]=1
    ((count+=1))
  fi
done

# No deletion is attempted before every archive and every date has passed the
# checks above. Extra pinned backups remain outside the normal ten-point limit.
for name in "${archives[@]}"; do
  if [[ ! ${keep[$name]+yes} ]]; then
    echo "Pruning verified excess backup: $name"
    rm -rf -- "$root/$name"
  fi
done
echo 'Retention complete.'
