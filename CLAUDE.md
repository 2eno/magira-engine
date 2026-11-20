# CLAUDE.md

## Tests starten

```sh
./scripts/test.sh
```

Führt alle Tests aus (dotnet test, GUT-Tests aus `game/tests` headless, Python-Tests aus `tools/tests`) und endet bei jedem Fehler mit Exit-Code ≠ 0. Der Godot-Befehl kommt aus `GODOT` (Standard `godot-mono`), z. B. `GODOT=/pfad/zu/godot ./scripts/test.sh`. Die CI (`.github/workflows/ci.yml`, Job `tests`) ruft dasselbe Skript auf. Neue Testarten werden in `scripts/test.sh` angehängt.
