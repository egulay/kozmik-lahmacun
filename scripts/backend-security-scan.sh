#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"
require_command mvn

declare -a scan_arguments=(
  "-Dmaven.repo.local=.m2"
  "org.owasp:dependency-check-maven:12.2.2:check"
  "-DfailBuildOnCVSS=7"
  "-DossindexAnalyzerEnabled=false"
  "-DassemblyAnalyzerEnabled=false"
  "-DretireJsAnalyzerEnabled=false"
  "-Dformats=HTML,JSON"
)

if [[ -n "${NVD_API_KEY:-}" ]]; then
  scan_arguments+=("-DnvdApiKeyEnvironmentVariable=NVD_API_KEY")
else
  printf '%s\n' \
    "NVD_API_KEY is not set. The first vulnerability database update may be slow." \
    "Set a free NVD API key in your shell for faster, reliable updates."
fi

cd "${REPOSITORY_ROOT}/backend"
exec mvn "${scan_arguments[@]}"
