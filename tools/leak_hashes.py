#!/usr/bin/env python3
"""Erzeugt aus einer Klartext-Namensliste eine Datei mit gesalzenen SHA-256-Hashes.

    python3 tools/leak_hashes.py --names namensliste.txt --salt salt.txt --out namen.hashes

Pro Name wird sha256(salt + normalisierter_name) geschrieben (hex, eine Zeile
pro Hash, sortiert und ohne Duplikate, damit die Reihenfolge der Liste nicht
durchsickert). Normalisierung: Unicode NFC, Kleinschreibung, Leerraum zu einem
Leerzeichen zusammengefasst. Leere Zeilen und Zeilen mit '#' werden uebersprungen.

Das Skript gibt niemals Namen aus, nur Anzahlen und Zeilennummern.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from leak_common import MAX_WOERTER, hash_name, ist_auffindbar, lies_liste, lies_salt  # noqa: E402

KOPFZEILE = "# leak_hashes v1: sha256(salt + name), name normalisiert (NFC, lower, Leerraum)\n"


def erzeuge_hashes(namen, salt):
    return sorted({hash_name(salt, name) for _, name in namen})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--names", required=True, help="Klartext-Namensliste, ein Name pro Zeile")
    parser.add_argument("--salt", required=True, help="Datei mit dem Salt")
    parser.add_argument("--out", required=True, help="Ausgabedatei fuer die Hashes")
    args = parser.parse_args(argv)

    try:
        salt = lies_salt(args.salt)
        namen = lies_liste(args.names)
    except (OSError, ValueError) as e:
        print("Fehler: %s" % e, file=sys.stderr)
        return 2

    # Warnen, wenn ein Name von leak_check nicht gefunden werden kann
    # (zu viele Woerter, Ziffern, Satzzeichen ...). Nur Zeilennummern ausgeben.
    nicht_auffindbar = [nr for nr, name in namen if not ist_auffindbar(name)]
    if nicht_auffindbar:
        print(
            "Warnung: %d Eintrag/Eintraege kann leak_check nicht finden "
            "(mehr als %d Woerter oder Zeichen ausser Buchstaben, Leerzeichen, '-' und \"'\"). "
            "Zeilen in %s: %s"
            % (len(nicht_auffindbar), MAX_WOERTER, args.names, ", ".join(map(str, nicht_auffindbar))),
            file=sys.stderr,
        )

    hashes = erzeuge_hashes(namen, salt)
    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        f.write(KOPFZEILE)
        for h in hashes:
            f.write(h + "\n")

    print("%d Hashes nach %s geschrieben." % (len(hashes), args.out), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
