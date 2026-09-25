# Shared options for the build_*war.sh entry points. Source after project_dir.
include_jvm=false
# Callers use ${packaging_options[@]+"${packaging_options[@]}"} so an empty
# array also works with set -u on macOS's Bash 3.2.
packaging_options=()
for option in "$@"; do
  case "$option" in
    --include-jvm)
      include_jvm=true
      packaging_options=(--include-jvm)
      ;;
    -h|--help)
      echo "Usage: bash $(basename "$0") [--include-jvm]"
      echo 'Build a DEX-only Android WAR by default.'
      echo '  --include-jvm  Also retain the original JVM classes and dependency JARs.'
      exit 0
      ;;
    *)
      echo "Unknown option: $option. Use --help for usage." >&2
      exit 2
      ;;
  esac
done
