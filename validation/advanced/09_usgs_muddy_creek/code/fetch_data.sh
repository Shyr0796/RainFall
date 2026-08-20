#!/usr/bin/env bash
set -euo pipefail

experiment_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
raw_dir="$experiment_dir/data/raw"
metadata="$raw_dir/sciencebase_item.json"
mkdir -p "$raw_dir"

if [[ ! -s "$metadata" ]]; then
  curl --fail --location --silent --show-error \
    'https://www.sciencebase.gov/catalog/item/621e85ded34ee0c6b389a988?format=json' \
    --output "$metadata"
fi

files=(
  MuddyCreek_model_performance_calibration_metrics.zip
  MuddyCreek_inundation_extents.zip
  MuddyCreek_inundation_depths.zip
  Muddy_Creek_summary_tables.zip
  RevisionHistory_v2.0.txt
  MuddyCreek_Harrisonville_geospatialdata_model_archive.xml
)

if [[ "${1:-}" == "--full" ]]; then
  files+=(MuddyCreek_normal_existing_conditions.zip)
fi

for name in "${files[@]}"; do
  uri="$(jq -r --arg name "$name" '.files[] | select(.name == $name) | .downloadUri' "$metadata")"
  expected="$(jq -r --arg name "$name" '.files[] | select(.name == $name) | .checksum.value' "$metadata")"
  target="$raw_dir/$name"
  if [[ ! -s "$target" ]]; then
    curl --fail --location --silent --show-error "$uri" --output "$target"
  elif [[ "$(md5sum "$target" | awk '{print $1}')" != "$expected" && "$name" == *.zip ]]; then
    echo "RESUME $name current_bytes=$(stat -c %s "$target")"
    curl --fail --location --silent --show-error --continue-at - "$uri" --output "$target"
  fi
  actual="$(md5sum "$target" | awk '{print $1}')"
  if [[ "$actual" != "$expected" ]]; then
    if [[ "$name" == "MuddyCreek_Harrisonville_geospatialdata_model_archive.xml" ]]; then
      echo "WARN publisher MD5 drift: $name expected=$expected downloaded=$actual bytes=$(stat -c %s "$target")"
      continue
    fi
    echo "MD5 mismatch: $name expected=$expected actual=$actual" >&2
    exit 1
  fi
  echo "PASS $name bytes=$(stat -c %s "$target") md5=$actual"
done
