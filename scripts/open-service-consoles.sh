#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

if [[ "$(uname -s)" != "Darwin" ]] || ! command -v osascript >/dev/null 2>&1; then
  echo "Automatic zsh service tabs require macOS and iTerm2." >&2
  exit 1
fi

quoted_root="$(printf '%q' "${REPOSITORY_ROOT}")"
readonly infrastructure_logs="cd ${quoted_root} && docker compose --env-file .env -f infrastructure/compose.yaml logs --follow --tail 100 vault postgres redis kafka minio mailpit keycloak"
requested_services=("$@")
if (( ${#requested_services[@]} == 0 )); then
  requested_services=(infrastructure java python frontend)
fi

requested() {
  local expected="$1"
  local item
  for item in "${requested_services[@]}"; do
    if [[ "${item}" == "${expected}" ]]; then
      return 0
    fi
  done
  return 1
}

open_iterm_tab() {
  local title="$1"
  local command="$2"
  osascript - "${title}" "${command}" <<'APPLESCRIPT'
on run arguments
    set tabTitle to item 1 of arguments
    set shellCommand to item 2 of arguments
    tell application "iTerm2"
        activate
        if (count of windows) is 0 then
            set targetWindow to (create window with default profile)
        else
            set targetWindow to current window
        end if
        tell targetWindow
            set serviceTab to (create tab with default profile)
            tell current session of serviceTab
                set name to tabTitle
                write text "exec /bin/zsh -lc " & quoted form of shellCommand
            end tell
        end tell
    end tell
end run
APPLESCRIPT
}

if requested infrastructure && ! open_iterm_tab "Kozmik Infrastructure" \
  "${infrastructure_logs}"; then
  echo "Could not open iTerm2 tabs automatically."
  echo "Ensure iTerm2 is installed and allow Automation access if macOS requests it."
  echo "Follow logs manually with:"
  echo "  docker compose --env-file .env -f infrastructure/compose.yaml --profile full-demo logs --follow"
  exit 1
fi

if requested java; then
  open_iterm_tab "Kozmik Java" \
    "cd ${quoted_root} && exec ./scripts/backend-dev.sh"
fi
if requested python; then
  open_iterm_tab "Kozmik Python" \
    "cd ${quoted_root} && exec ./scripts/executor-dev.sh"
fi
if requested frontend; then
  open_iterm_tab "Kozmik Frontend" \
    "cd ${quoted_root} && exec ./scripts/frontend-dev.sh"
fi

echo "Opened requested iTerm2 zsh tabs: ${requested_services[*]}."
