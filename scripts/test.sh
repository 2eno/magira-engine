#!/usr/bin/env bash
# Führt alle Tests des Repos aus – lokal und in der CI.
# Endet mit Exit-Code != 0, sobald eine Testart fehlschlägt.
# Neue Testarten werden hier als weitere run_suite-Zeile angehängt.
#
# Umgebung:
#   GODOT  Godot-.NET-Befehl (Standard: godot-mono)
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GODOT="${GODOT:-godot-mono}"
cd "$ROOT"

failed=()

run_suite() {
	local name="$1"; shift
	[[ -n "${GITHUB_ACTIONS:-}" ]] && echo "::group::${name}"
	echo "==> ${name}"
	if "$@"; then
		echo "==> ${name}: OK"
	else
		echo "==> ${name}: FEHLGESCHLAGEN (Exit $?)" >&2
		failed+=("$name")
	fi
	[[ -n "${GITHUB_ACTIONS:-}" ]] && echo "::endgroup::"
	return 0
}

dotnet_tests() {
	dotnet test
}

gut_tests() {
	if ! command -v "$GODOT" >/dev/null 2>&1; then
		echo "Godot-Befehl '$GODOT' nicht gefunden (GODOT setzen)." >&2
		return 1
	fi
	# GUT braucht importierte class_names; ohne Import beendet es sich mit Exit 0.
	if [[ ! -f game/.godot/global_script_class_cache.cfg ]]; then
		"$GODOT" --headless --path game --import || return 1
	fi
	local junit
	junit="$(mktemp -d)/gut-junit.xml"
	"$GODOT" --headless --path game \
		-s res://addons/gut/gut_cmdln.gd \
		-gconfig= \
		-gdir=res://tests -ginclude_subdirs \
		-gjunit_xml_file="$junit" \
		-gexit || return 1
	# GUT kann in Sonderfällen (fehlender Import, Ladefehler) mit 0 enden,
	# ohne Tests auszuführen. Der JUnit-Bericht beweist, dass Tests liefen.
	if [[ ! -s "$junit" ]]; then
		echo "GUT hat keinen Bericht geschrieben – Tests wurden nicht ausgeführt." >&2
		return 1
	fi
	if grep -q '<testsuites[^>]* tests="0"' "$junit"; then
		echo "GUT hat keine Tests in game/tests gefunden." >&2
		return 1
	fi
}

python_tests() {
	python3 -m unittest discover -s tools/tests
}

run_suite "dotnet test" dotnet_tests
run_suite "GUT (game/tests)" gut_tests
run_suite "Python (tools/tests)" python_tests

if ((${#failed[@]})); then
	echo "Fehlgeschlagen: ${failed[*]}" >&2
	exit 1
fi
echo "Alle Tests bestanden."
