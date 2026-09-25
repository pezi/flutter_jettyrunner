#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "$0")/.." && pwd)"
source "$project_dir/scripts/war_build_options.sh"
sdk_dir="${ANDROID_SDK_ROOT:-${ANDROID_HOME:-}}"
if [[ -z "$sdk_dir" && -f "$project_dir/../warrunner/android/local.properties" ]]; then
  sdk_dir="$(sed -n 's/^sdk.dir=//p' "$project_dir/../warrunner/android/local.properties")"
fi
if [[ -z "$sdk_dir" ]]; then
  echo 'Set ANDROID_SDK_ROOT or ANDROID_HOME to your Android SDK directory.' >&2
  exit 1
fi
d8="$sdk_dir/build-tools/${ANDROID_BUILD_TOOLS:-36.0.0}/d8"
android_jar="$sdk_dir/platforms/android-${ANDROID_COMPILE_API:-36}/android.jar"
if [[ ! -x "$d8" || ! -f "$android_jar" ]]; then
  echo "Missing Android tools: $d8 or $android_jar" >&2
  exit 1
fi

mvn -B -f "$project_dir/vaadin-bookstore-demo/pom.xml" clean package
python3 "$project_dir/scripts/package_android_war.py" \
  "$project_dir/vaadin-bookstore-demo/target/vaadin-bookstore-demo.war" \
  "$project_dir/war_repository/vaadin-bookstore-demo.war" \
  --d8 "$d8" --android-jar "$android_jar" \
  --classpath "$project_dir/vaadin-bookstore-demo/target/d8-classpath" \
  --asm-jar "$project_dir/vaadin-bookstore-demo/target/android-tools/asm-9.9.jar" \
  ${packaging_options[@]+"${packaging_options[@]}"}
