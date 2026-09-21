#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "$0")/.." && pwd)"
sdk_dir="${ANDROID_SDK_ROOT:-${ANDROID_HOME:-}}"
if [[ -z "$sdk_dir" && -f "$project_dir/../jettyrunner/android/local.properties" ]]; then
  sdk_dir="$(sed -n 's/^sdk.dir=//p' "$project_dir/../jettyrunner/android/local.properties")"
fi
if [[ -z "$sdk_dir" ]]; then
  echo 'Set ANDROID_SDK_ROOT or ANDROID_HOME to your Android SDK directory.' >&2
  exit 1
fi
build_tools="${ANDROID_BUILD_TOOLS:-36.0.0}"
d8="$sdk_dir/build-tools/$build_tools/d8"
if [[ ! -x "$d8" ]]; then
  echo "Missing $d8. Install Android SDK Build-Tools $build_tools or set ANDROID_BUILD_TOOLS." >&2
  exit 1
fi

mvn -B -f "$project_dir/servlet/pom.xml" clean package
target_dir="$project_dir/servlet/target"
jar --create --file "$target_dir/servlet-classes.jar" -C "$target_dir/classes" .
mkdir -p "$target_dir/dex" "$project_dir/war_repository"
"$d8" --release --min-api 34 \
  --classpath "$target_dir/d8-classpath/jakarta.servlet-api-5.0.0.jar" \
  --output "$target_dir/dex" "$target_dir/servlet-classes.jar"

# Keep a standard JVM WAR as well as Android DEX, with stable ZIP timestamps.
python3 - "$target_dir/hello.war" "$target_dir/dex/classes.dex" "$project_dir/war_repository/hello.war" <<'PY'
import pathlib
import sys
import zipfile

source, dex, destination = map(pathlib.Path, sys.argv[1:])
temporary = destination.with_suffix('.war.tmp')
with zipfile.ZipFile(source) as original, zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as output:
    entries = {entry.filename: original.read(entry) for entry in original.infolist()}
    entries['classes.dex'] = dex.read_bytes()
    for name, content in sorted(entries.items()):
        entry = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
        entry.compress_type = zipfile.ZIP_DEFLATED
        entry.external_attr = 0o100644 << 16
        output.writestr(entry, content)
temporary.replace(destination)
print(f'Built {destination} ({destination.stat().st_size} bytes)')
PY
