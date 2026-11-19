#!/usr/bin/env python3
"""Sucht in Textdateien nach Namen aus einer Klartextliste oder einer Hash-Datei.

    python3 tools/leak_check.py --names klartext.txt [--root .] [--staged]
    python3 tools/leak_check.py --hashes namen.hashes --salt salt.txt [--root .] [--staged]
        [--ignore erlaubt.txt] [--zeige-woerter]

Aus jedem Text werden alle Wortfolgen aus 1 bis 4 Woertern gebildet, normalisiert
(NFC, Kleinschreibung, Leerraum) und mit der Liste bzw. den Hashes verglichen.
Woerter werden auf zwei Arten gebildet: mit Bindestrich/Apostroph als ein Wort
("Jean-Luc") und als reine Buchstabenfolgen, auch an Unterstrichen und
CamelCase-Grenzen geteilt ("npc_MaxMuster" -> "npc", "max", "muster").

Ausgabe pro Treffer nur "Datei:Zeile" - ohne das Wort, weil die Ausgabe auch in
Logs oder bei einer KI landen kann. Mit --zeige-woerter kommt das Wort dazu.

Exit-Code: 0 = keine Treffer, 1 = Treffer, 2 = Fehler.
"""

import argparse
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from leak_common import hash_name, kandidaten, lies_hashes, lies_liste, lies_salt  # noqa: E402

ENDUNGEN = {".gd", ".cs", ".md", ".json", ".tres", ".tscn", ".cfg", ".txt", ".py", ".yml", ".yaml"}
IGNORIERTE_ORDNER = {".git", ".godot", ".mono", "bin", "obj"}
IGNORIERTE_PFADE = {"game/addons"}


def ist_ignoriert(relpfad):
    """relpfad mit '/' als Trenner, relativ zu --root."""
    teile = relpfad.split("/")
    if any(t in IGNORIERTE_ORDNER for t in teile[:-1]):
        return True
    return any(relpfad == p or relpfad.startswith(p + "/") for p in IGNORIERTE_PFADE)


def ist_textdatei(relpfad):
    return os.path.splitext(relpfad)[1].lower() in ENDUNGEN


def dateien_im_baum(root):
    for ordner, unterordner, dateien in os.walk(root):
        rel_ordner = os.path.relpath(ordner, root).replace(os.sep, "/")
        rel_ordner = "" if rel_ordner == "." else rel_ordner + "/"
        unterordner[:] = sorted(
            u for u in unterordner
            if u not in IGNORIERTE_ORDNER and not ist_ignoriert(rel_ordner + u + "/x")
        )
        for name in sorted(dateien):
            rel = rel_ordner + name
            if ist_textdatei(rel) and not ist_ignoriert(rel):
                yield rel


def _git(root, *args):
    return subprocess.run(["git", "-C", root] + list(args), check=True, capture_output=True).stdout


def gestagte_dateien(root):
    ausgabe = _git(root, "diff", "--cached", "--name-only", "--diff-filter=ACMR", "--relative", "-z")
    for rel in ausgabe.decode("utf-8", "surrogateescape").split("\0"):
        if rel and ist_textdatei(rel) and not ist_ignoriert(rel):
            yield rel


def lies_datei(root, rel, staged):
    if staged:
        daten = _git(root, "show", ":./" + rel)
    else:
        with open(os.path.join(root, rel), "rb") as f:
            daten = f.read()
    if b"\0" in daten:
        return None  # binaer
    return daten.decode("utf-8", "replace")


class Pruefer:
    def __init__(self, namen=None, hashes=None, salt=None, erlaubt=()):
        self.namen = set(namen or ())
        self.hashes = set(hashes or ())
        self.salt = salt
        self.erlaubt = set(erlaubt)
        self._cache = {}

    def ist_treffer(self, wortfolge):
        if wortfolge in self.erlaubt:
            return False
        ergebnis = self._cache.get(wortfolge)
        if ergebnis is None:
            if self.namen and wortfolge in self.namen:
                ergebnis = True
            elif self.hashes:
                ergebnis = hash_name(self.salt, wortfolge) in self.hashes
            else:
                ergebnis = False
            self._cache[wortfolge] = ergebnis
        return ergebnis

    def pruefe_text(self, text):
        """Liefert sortierte Liste (zeile, wortfolge) der Treffer."""
        return sorted((z, w) for z, w in kandidaten(text) if self.ist_treffer(w))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    quelle = parser.add_mutually_exclusive_group(required=True)
    quelle.add_argument("--names", help="Klartext-Namensliste")
    quelle.add_argument("--hashes", help="Hash-Datei von leak_hashes.py (braucht --salt)")
    parser.add_argument("--salt", help="Salt-Datei (nur mit --hashes)")
    parser.add_argument("--root", default=".", help="Wurzelverzeichnis (Standard: .)")
    parser.add_argument("--staged", action="store_true", help="nur gestagte Dateien (Inhalt aus dem Index)")
    parser.add_argument("--ignore", help="Liste erlaubter Woerter/Wortfolgen")
    parser.add_argument("--zeige-woerter", action="store_true", help="gefundene Woerter mit ausgeben")
    args = parser.parse_args(argv)

    if args.hashes and not args.salt:
        parser.error("--hashes braucht --salt")
    if args.names and args.salt:
        parser.error("--salt nur zusammen mit --hashes")

    root = os.path.abspath(args.root)
    try:
        erlaubt = [w for _, w in lies_liste(args.ignore)] if args.ignore else []
        if args.names:
            pruefer = Pruefer(namen=[n for _, n in lies_liste(args.names)], erlaubt=erlaubt)
        else:
            pruefer = Pruefer(hashes=lies_hashes(args.hashes), salt=lies_salt(args.salt), erlaubt=erlaubt)
    except (OSError, ValueError) as e:
        print("Fehler: %s" % e, file=sys.stderr)
        return 2

    # Die Eingabedateien selbst nicht durchsuchen, falls sie im Baum liegen.
    eigene = {os.path.realpath(p) for p in (args.names, args.hashes, args.salt, args.ignore) if p}

    try:
        dateien = list(gestagte_dateien(root) if args.staged else dateien_im_baum(root))
    except (OSError, subprocess.CalledProcessError) as e:
        print("Fehler beim Auflisten der Dateien: %s" % e, file=sys.stderr)
        return 2

    treffer_gesamt = 0
    dateien_mit_treffern = 0
    for rel in dateien:
        if os.path.realpath(os.path.join(root, rel)) in eigene:
            continue
        try:
            text = lies_datei(root, rel, args.staged)
        except (OSError, subprocess.CalledProcessError) as e:
            print("Warnung: %s nicht lesbar (%s)" % (rel, e.__class__.__name__), file=sys.stderr)
            continue
        if text is None:
            continue
        treffer = pruefer.pruefe_text(text)
        if not treffer:
            continue
        dateien_mit_treffern += 1
        if args.zeige_woerter:
            for zeile, wort in treffer:
                print("%s:%d: %s" % (rel, zeile, wort))
            treffer_gesamt += len(treffer)
        else:
            zeilen = sorted({z for z, _ in treffer})
            for zeile in zeilen:
                print("%s:%d" % (rel, zeile))
            treffer_gesamt += len(zeilen)

    if treffer_gesamt:
        print("%d Treffer in %d Datei(en)." % (treffer_gesamt, dateien_mit_treffern), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
