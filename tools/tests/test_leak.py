"""Tests fuer leak_hashes.py und leak_check.py - nur mit frei erfundenen Namen.

Ausfuehren: python3 -m unittest discover -s tools/tests
"""

import contextlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import unittest

TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TOOLS)

import leak_check  # noqa: E402
import leak_hashes  # noqa: E402
from leak_common import hash_name, ist_auffindbar, kandidaten, normalisiere  # noqa: E402

ERFUNDENE_NAMEN = """\
# frei erfundene Testnamen
Brunhilde   Quarzfeld
Jean-Luc Pfeffermühl
Zorbo

Élodie Wackelstein
Xantippa
"""
SALT = "test-salt-1234\n"


def schreibe(pfad, inhalt, binaer=False):
    os.makedirs(os.path.dirname(pfad), exist_ok=True)
    with open(pfad, "wb" if binaer else "w", **({} if binaer else {"encoding": "utf-8"})) as f:
        f.write(inhalt)


def starte(modul, argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = modul.main(argv)
    return code, out.getvalue(), err.getvalue()


class TestNormalisierung(unittest.TestCase):
    def test_klein_und_leerraum(self):
        self.assertEqual(normalisiere("  Brunhilde \t QUARZFELD\n"), "brunhilde quarzfeld")

    def test_nfc(self):
        nfd = unicodedata.normalize("NFD", "Élodie")
        self.assertNotEqual(nfd, "Élodie")
        self.assertEqual(normalisiere(nfd), "élodie")

    def test_hash_ist_salt_plus_name(self):
        import hashlib
        self.assertEqual(hash_name(b"s", "zorbo"), hashlib.sha256(b"szorbo").hexdigest())


class TestKandidaten(unittest.TestCase):
    def woerter(self, text):
        return {w for _, w in kandidaten(text)}

    def test_ein_bis_vier_woerter(self):
        w = self.woerter("eins zwei drei vier fuenf")
        self.assertIn("eins", w)
        self.assertIn("eins zwei drei vier", w)
        self.assertNotIn("eins zwei drei vier fuenf", w)

    def test_bindestrich_und_einzelteile(self):
        w = self.woerter('var npc = "Jean-Luc"')
        self.assertIn("jean-luc", w)
        self.assertIn("jean", w)
        self.assertIn("luc", w)

    def test_snake_und_camel_case(self):
        w = self.woerter("var npc_brunhildeQuarzfeld = 1; class ZorboXantippaNPC")
        self.assertIn("brunhilde quarzfeld", w)
        self.assertIn("zorbo xantippa", w)
        self.assertIn("npc", w)

    def test_zeilennummer_und_umbruch(self):
        k = kandidaten("erste zeile\nhallo Brunhilde\nQuarzfeld ende")
        self.assertIn((2, "brunhilde quarzfeld"), k)
        self.assertIn((3, "quarzfeld"), k)

    def test_auffindbar(self):
        self.assertTrue(ist_auffindbar("jean-luc pfeffermühl"))
        self.assertFalse(ist_auffindbar("a b c d e"))
        self.assertFalse(ist_auffindbar("agent 007"))


class Basis(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.eingabe = os.path.join(self.tmp, "eingabe")
        self.root = os.path.join(self.tmp, "repo")
        os.makedirs(self.root)
        self.namen = os.path.join(self.eingabe, "namen.txt")
        self.salt = os.path.join(self.eingabe, "salt.txt")
        self.hashes = os.path.join(self.eingabe, "namen.hashes")
        schreibe(self.namen, ERFUNDENE_NAMEN)
        schreibe(self.salt, SALT)

    def datei(self, rel, inhalt, binaer=False):
        schreibe(os.path.join(self.root, rel), inhalt, binaer)


class TestLeakHashes(Basis):
    def test_erzeugt_sortierte_hashes(self):
        code, out, err = starte(leak_hashes, ["--names", self.namen, "--salt", self.salt, "--out", self.hashes])
        self.assertEqual(code, 0)
        with open(self.hashes, encoding="utf-8") as f:
            zeilen = [z.strip() for z in f if not z.startswith("#")]
        self.assertEqual(len(zeilen), 5)
        self.assertEqual(zeilen, sorted(zeilen))
        self.assertIn(hash_name(b"test-salt-1234", "brunhilde quarzfeld"), zeilen)
        self.assertNotIn("brunhilde", (out + err).lower())

    def test_warnt_ohne_namen_zu_nennen(self):
        schreibe(self.namen, "Zorbo\nAgent Siebenundneunzig 9\n")
        code, out, err = starte(leak_hashes, ["--names", self.namen, "--salt", self.salt, "--out", self.hashes])
        self.assertEqual(code, 0)
        self.assertIn("Warnung", err)
        self.assertIn(": 2", err)
        self.assertNotIn("siebenundneunzig", (out + err).lower())

    def test_leerer_salt(self):
        schreibe(self.salt, "\n")
        code, _, _ = starte(leak_hashes, ["--names", self.namen, "--salt", self.salt, "--out", self.hashes])
        self.assertEqual(code, 2)


class TestLeakCheck(Basis):
    def setUp(self):
        super().setUp()
        self.datei("game/scripts/npc.gd", "extends Node\n\nvar name = \"Brunhilde  Quarzfeld\"\n")
        self.datei("docs/lore.md", "Kein Name hier.\nAber der Held heißt " +
                   unicodedata.normalize("NFD", "ÉLODIE wackelstein") + ".\n")
        self.datei("data/sauber.json", '{"titel": "Nichts zu sehen"}\n')
        # ignorierte Orte und Endungen
        self.datei("game/addons/plugin/x.gd", "Zorbo\n")
        self.datei("game/.godot/cache.cfg", "Zorbo\n")
        self.datei("bin/a.txt", "Zorbo\n")
        self.datei("src/obj/b.cs", "Zorbo\n")
        self.datei("bild.png", "Zorbo\n")
        self.datei("binaer.txt", b"Zorbo\0\x01", binaer=True)

    def check(self, *extra):
        return starte(leak_check, ["--root", self.root] + list(extra))

    def erwartet(self, out):
        return sorted(out.splitlines())

    def test_klartext(self):
        code, out, err = self.check("--names", self.namen)
        self.assertEqual(code, 1)
        self.assertEqual(self.erwartet(out), ["docs/lore.md:2", "game/scripts/npc.gd:3"])
        self.assertNotIn("quarzfeld", (out + err).lower())
        self.assertNotIn("wackelstein", (out + err).lower())

    def test_hashes_gleiches_ergebnis(self):
        starte(leak_hashes, ["--names", self.namen, "--salt", self.salt, "--out", self.hashes])
        code, out, _ = self.check("--hashes", self.hashes, "--salt", self.salt)
        self.assertEqual(code, 1)
        self.assertEqual(self.erwartet(out), ["docs/lore.md:2", "game/scripts/npc.gd:3"])

    def test_falscher_salt_findet_nichts(self):
        starte(leak_hashes, ["--names", self.namen, "--salt", self.salt, "--out", self.hashes])
        schreibe(self.salt, "anderer-salt")
        code, out, _ = self.check("--hashes", self.hashes, "--salt", self.salt)
        self.assertEqual((code, out), (0, ""))

    def test_zeige_woerter(self):
        code, out, _ = self.check("--names", self.namen, "--zeige-woerter")
        self.assertEqual(code, 1)
        self.assertIn("game/scripts/npc.gd:3: brunhilde quarzfeld", out)
        self.assertIn("docs/lore.md:2: élodie wackelstein", out)

    def test_ignore_liste(self):
        erlaubt = os.path.join(self.eingabe, "erlaubt.txt")
        schreibe(erlaubt, "Brunhilde Quarzfeld\n")
        code, out, _ = self.check("--names", self.namen, "--ignore", erlaubt)
        self.assertEqual(code, 1)
        self.assertEqual(self.erwartet(out), ["docs/lore.md:2"])

    def test_keine_treffer(self):
        schreibe(self.namen, "Gibtsnichtname\n")
        code, out, _ = self.check("--names", self.namen)
        self.assertEqual((code, out), (0, ""))

    def test_eingabedateien_im_baum_werden_uebersprungen(self):
        namen_im_repo = os.path.join(self.root, "namen.txt")
        schreibe(namen_im_repo, ERFUNDENE_NAMEN)
        code, out, _ = self.check("--names", namen_im_repo)
        self.assertNotIn("namen.txt", out)

    def test_salt_ohne_hashes_ist_fehler(self):
        with self.assertRaises(SystemExit) as cm:
            self.check("--names", self.namen, "--salt", self.salt)
        self.assertEqual(cm.exception.code, 2)


@unittest.skipUnless(shutil.which("git"), "git nicht installiert")
class TestStaged(Basis):
    def git(self, *args):
        subprocess.run(["git", "-C", self.root] + list(args), check=True, capture_output=True)

    def test_nur_gestagter_inhalt(self):
        self.git("init", "-q")
        self.datei("a.gd", "Zorbo\n")          # gestagt mit Treffer
        self.datei("b.gd", "sauber\n")         # gestagt ohne Treffer, danach im Arbeitsbaum veraendert
        self.datei("c.gd", "Xantippa\n")       # nicht gestagt
        self.git("add", "a.gd", "b.gd")
        self.datei("b.gd", "jetzt Zorbo\n")
        code, out, _ = starte(leak_check, ["--root", self.root, "--staged", "--names", self.namen])
        self.assertEqual(code, 1)
        self.assertEqual(out.splitlines(), ["a.gd:1"])


if __name__ == "__main__":
    unittest.main()
