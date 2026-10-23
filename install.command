#!/bin/bash
# macOS launcher; no sudo, curl installer, PATH rewrite or optional tool install.
set -u
it3d_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
it3d_check_only=false
for it3d_arg in "$@"; do
  if [[ "$it3d_arg" == '--check-only' ]]; then it3d_check_only=true; fi
done
it3d_python=''
it3d_probe() {
  [[ -x "$1" ]] || return 1
  if [[ "$1" == '/usr/bin/python3' ]] && ! /usr/bin/xcode-select -p >/dev/null 2>&1; then return 1; fi
  "$1" -B -c 'import sys; sys.exit(sys.version_info < (3,10))' >/dev/null 2>&1
}
if [[ -n "${IMAGE_TO_3D_PYTHON:-}" ]]; then
  if ! it3d_probe "$IMAGE_TO_3D_PYTHON"; then
    echo 'IMAGE_TO_3D_PYTHON must be an executable Python 3.10+ path.' >&2; exit 2
  fi
  it3d_python="$IMAGE_TO_3D_PYTHON"
else
  for it3d_candidate in "$(command -v python3 || true)" /opt/homebrew/opt/python@3.13/bin/python3.13 /usr/local/opt/python@3.13/bin/python3.13; do
    if [[ -n "$it3d_candidate" ]] && it3d_probe "$it3d_candidate"; then it3d_python="$it3d_candidate"; break; fi
  done
fi
if [[ -z "$it3d_python" ]]; then
  if "$it3d_check_only"; then echo 'Python 3.10+ missing; check-only made no changes.' >&2; exit 2; fi
  it3d_brew="$(command -v brew || true)"
  if [[ -z "$it3d_brew" ]]; then
    for it3d_candidate in /opt/homebrew/bin/brew /usr/local/bin/brew; do
      if [[ -x "$it3d_candidate" ]]; then it3d_brew="$it3d_candidate"; break; fi
    done
  fi
  if [[ -z "$it3d_brew" ]]; then
    echo 'Python 3.10+ and Homebrew are unavailable. Nothing was installed.' >&2
    echo 'Install Python from https://www.python.org/downloads/macos/ then rerun this launcher.' >&2
    exit 2
  fi
  echo "Python 3.10+ missing. Proposed command: $it3d_brew install python@3.13"
  echo 'This changes the existing Homebrew prefix and may install required formula dependencies.'
  echo 'No Homebrew installation, sudo, shell profile edits or optional tools.'
  if [[ ! -t 0 ]]; then echo 'No interactive terminal: no installation approved.' >&2; exit 2; fi
  read -r -p 'Type INSTALL to install Python; Enter cancels: ' it3d_answer
  if [[ "$it3d_answer" != 'INSTALL' ]]; then echo 'Cancelled; nothing installed.'; exit 2; fi
  if ! HOMEBREW_NO_AUTO_UPDATE=1 "$it3d_brew" install python@3.13; then echo 'Python installation failed; no automatic retry.' >&2; exit 2; fi
  it3d_prefix="$("$it3d_brew" --prefix python@3.13)" || exit 2
  it3d_python="$it3d_prefix/bin/python3.13"
  if ! it3d_probe "$it3d_python"; then echo 'New Python could not be validated. Rerun with IMAGE_TO_3D_PYTHON set to its path.' >&2; exit 2; fi
fi
exec "$it3d_python" -B -X utf8 "$it3d_dir/scripts/setup_skill.py" "$@"
