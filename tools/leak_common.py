"""Gemeinsame Funktionen fuer leak_hashes.py und leak_check.py.

Wichtig: Diese Funktionen geben nie Namen aus. Alle Meldungen, die Namen
betreffen koennten, nennen hoechstens Dateien und Zeilennummern.
"""

import bisect
import hashlib
import re
import unicodedata

MAX_WOERTER = 4

# Ein Wort besteht nur aus Buchstaben (keine Ziffern, kein Unterstrich).
_BUCHSTABEN = r"[^\W\d_]+"
# Variante A: Bindestrich- und Apostroph-Verbindungen bleiben ein Wort
# ("Jean-Luc", "O'Brien").
_WORT_VERBUND = re.compile(_BUCHSTABEN + r"(?:['’\-]" + _BUCHSTABEN + r")*")
# Variante B: reine Buchstabenfolgen, zusaetzlich an CamelCase-Grenzen geteilt
# ("npc_MaxMustermann" -> "npc", "Max", "Mustermann").
_WORT_EINFACH = re.compile(_BUCHSTABEN)


def normalisiere(text):
    """Unicode NFC, Kleinschreibung, Leerraum zu einem Leerzeichen zusammengefasst."""
    text = unicodedata.normalize("NFC", text)
    text = text.lower()
    text = unicodedata.normalize("NFC", text)
    return " ".join(text.split())


def lies_salt(pfad):
    with open(pfad, "rb") as f:
        salt = f.read().strip()
    if not salt:
        raise ValueError("Salt-Datei ist leer: %s" % pfad)
    return salt


def hash_name(salt, normalisierter_name):
    return hashlib.sha256(salt + normalisierter_name.encode("utf-8")).hexdigest()


def lies_liste(pfad):
    """Liefert (zeilennummer, normalisierter_eintrag) fuer jede nicht-leere,
    nicht auskommentierte Zeile."""
    eintraege = []
    with open(pfad, encoding="utf-8-sig") as f:
        for nr, zeile in enumerate(f, 1):
            if zeile.lstrip().startswith("#"):
                continue
            norm = normalisiere(zeile)
            if norm:
                eintraege.append((nr, norm))
    return eintraege


def lies_hashes(pfad):
    hashes = set()
    with open(pfad, encoding="utf-8") as f:
        for zeile in f:
            zeile = zeile.strip().lower()
            if zeile and not zeile.startswith("#"):
                hashes.add(zeile)
    return hashes


def _zeilenanfaenge(text):
    anfaenge = [0]
    pos = text.find("\n")
    while pos != -1:
        anfaenge.append(pos + 1)
        pos = text.find("\n", pos + 1)
    return anfaenge


def _camel_teile(wort, start):
    """Teilt ein Wort an CamelCase-Grenzen. Liefert (offset, teilwort)."""
    teile = []
    anfang = 0
    for i in range(1, len(wort)):
        vorher, jetzt = wort[i - 1], wort[i]
        naechstes = wort[i + 1] if i + 1 < len(wort) else ""
        if (vorher.islower() and jetzt.isupper()) or (
            vorher.isupper() and jetzt.isupper() and naechstes.islower()
        ):
            teile.append((start + anfang, wort[anfang:i]))
            anfang = i
    teile.append((start + anfang, wort[anfang:]))
    return teile


def _token_folgen(text):
    """Liefert zwei Token-Listen [(offset, wort), ...] fuer die beiden Varianten."""
    verbund = [(m.start(), m.group()) for m in _WORT_VERBUND.finditer(text)]
    einfach = []
    for m in _WORT_EINFACH.finditer(text):
        einfach.extend(_camel_teile(m.group(), m.start()))
    return verbund, einfach


def kandidaten(text, max_woerter=MAX_WOERTER):
    """Liefert die Menge (zeile, normalisierte_wortfolge) aller Wortfolgen aus
    1 bis max_woerter Woertern. Wortfolgen duerfen ueber Zeilenumbrueche gehen;
    gemeldet wird die Zeile des ersten Wortes."""
    text = unicodedata.normalize("NFC", text)
    anfaenge = _zeilenanfaenge(text)
    ergebnis = set()
    for tokens in _token_folgen(text):
        woerter = [w for _, w in tokens]
        for i, (offset, _) in enumerate(tokens):
            zeile = bisect.bisect_right(anfaenge, offset)
            for n in range(1, max_woerter + 1):
                if i + n > len(woerter):
                    break
                ergebnis.add((zeile, normalisiere(" ".join(woerter[i:i + n]))))
    return ergebnis


def ist_auffindbar(normalisierter_name):
    """Prueft, ob leak_check diesen Namen ueberhaupt finden kann."""
    return any(k == normalisierter_name for _, k in kandidaten(normalisierter_name))
