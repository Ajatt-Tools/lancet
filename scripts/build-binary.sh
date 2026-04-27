#!/usr/bin/env bash
# Builds the Lancet single-file binary with PyInstaller.
#
# Auto-detects OS via $RUNNER_OS (in CI) or `uname -s` (locally) to choose
# the binary name and icon. Override with --name/--icon.

set -euo pipefail

if [[ ${BASH_VERSION%%.*} -lt 5 ]]; then
	echo "Bash version is older than 5. Exiting." >&2
	exit 1
fi

usage() {
	cat <<-EOF >&2
	Usage: scripts/build-binary.sh [options]

	Options:
	  -n, --name NAME  Override the output binary name (default: Lancet-<os>).
	  -i, --icon PATH  Override the icon file (default: lancet/icons/logo.{ico,png}).
	  -h, --help       Show this help message.
	EOF
}

detect_os() {
	local -r os="${RUNNER_OS:-$(uname -s)}"
	case "$os" in
		Windows | MINGW* | MSYS* | CYGWIN*) echo "windows" ;;
		Linux) echo "gnulinux" ;;
		Darwin | macOS) echo "macos" ;;
		*)
			echo "unsupported OS: $os" >&2
			exit 1
			;;
	esac
}

detect_icon() {
	case "$1" in
		windows) echo "lancet/icons/logo.ico" ;;
		*) echo "lancet/icons/logo.png" ;;
	esac
}

main() {
	cd -- "$(git rev-parse --show-toplevel)" || exit 1

	local -r os=$(detect_os)
	local -r icon=$(detect_icon "$os")
	local -r sep=$(python -c 'import os; print(os.pathsep)')
	local -r app_name="lancet-$os"

	while (($# > 0)); do
		case "$1" in
			-n | --name)
				app_name=${2:?--name requires a value}
				shift 2
				;;
			-i | --icon)
				icon=${2:?--icon requires a value}
				shift 2
				;;
			-h | --help)
				usage
				exit 0
				;;
			*)
				echo "unknown argument: $1" >&2
				usage
				exit 1
				;;
		esac
	done

	if ! [[ -f "$icon" ]]; then
		echo "icon not found: $icon" >&2
		exit 1
	fi

	local -a pyinstaller_args=(
		--noconfirm
		--onefile
		--windowed
		--name "$app_name"
		--icon "$icon"
		--add-data "lancet/icons${sep}lancet/icons"
		--add-data "lancet/lancet.desktop${sep}lancet"
		--hidden-import lancet
		--hidden-import comic_text_detector
	)

	if [[ "$os" != "windows" ]]; then
		# https://pyinstaller.org/en/stable/usage.html#cmdoption-s
		# The doc: not recommended for Windows
		pyinstaller_args+=(--strip)
	fi

	# https://pyinstaller.org/en/stable/usage.html#options
	pyinstaller "${pyinstaller_args[@]}" lancet/__main__.py
}

main "$@"
