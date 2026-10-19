import os, subprocess, tempfile, unittest
from pathlib import Path

from validate_mo import parse_mo, validate

PO = 'msgid ""\nmsgstr ""\n"Content-Type: text/plain; charset=UTF-8\\n"\n\nmsgid "hi"\nmsgstr "привет"\n\nmsgid "bye"\nmsgstr "пока"\n'


class Repo:
    def __init__(self, po=PO):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        (self.root / "m/lang").mkdir(parents=True)
        self.po, self.mo = self.root / "m/lang/ru_RU.po", self.root / "m/lang/ru_RU.mo"
        self.po.write_text(po)
        subprocess.run(["msgfmt", "-o", self.mo, self.po], check=True)

    def run(self, files=("m/lang/ru_RU.po", "m/lang/ru_RU.mo")): return validate(self.root, list(files))


class ValidateMo(unittest.TestCase):
    def repo(self, po=PO):
        r = Repo(po); self.addCleanup(r.tmp.cleanup); return r

    def test_matching_mo_passes_clean(self):
        errors, warnings, _ = self.repo().run()
        self.assertEqual((errors, warnings), ([], []))

    def test_trailing_bytes_fail(self):
        r = self.repo(); r.mo.write_bytes(r.mo.read_bytes() + b"MZ payload")
        self.assertIn("trailing bytes", r.run()[0][0][1])

    def test_hidden_gap_between_strings_fails(self):
        r = self.repo(); d = r.mo.read_bytes(); i = d.index("привет".encode())
        r.mo.write_bytes(d[:i] + b"X" + d[i:])
        self.assertTrue(r.run()[0])

    def test_bad_magic_fails(self):
        r = self.repo(); r.mo.write_bytes(b"\x00" * 64)
        self.assertIn("bad magic", r.run()[0][0][1])

    def test_invalid_utf8_fails(self):
        r = self.repo(); r.mo.write_bytes(r.mo.read_bytes().replace("пока".encode(), b"\xff\xfe\xfd\xfc\xfb\xfa\xf9\xf8"))
        self.assertTrue(r.run()[0])

    def test_non_mo_files_are_ignored(self):
        r = self.repo(); (r.root / "data.json").write_text("{}"); (r.root / "run.sh").write_text("x"); os.chmod(r.root / "run.sh", 0o755); (r.root / "link").symlink_to(r.po)
        self.assertEqual(r.run(["data.json", "run.sh", "link", "m/lang/ru_RU.po", "m/lang/ru_RU.mo"])[:2], ([], []))

    def test_symlink_and_exec_mo_fail(self):
        r = self.repo(); (r.root / "m/lang/a.mo").symlink_to(r.mo); os.chmod(r.mo, 0o755)
        self.assertEqual({e[1] for e in r.run(["m/lang/a.mo", "m/lang/ru_RU.mo"])[0]}, {"symlink", "executable bit set"})

    def test_po_mismatch_warns_with_counts_but_passes(self):
        r = self.repo(); r.po.write_text(PO.replace("пока", "бай") + '\nmsgid "new"\nmsgstr "новый"\n')
        errors, warnings, _ = r.run()
        self.assertEqual(errors, [])
        self.assertIn("1 missing, 0 extra, 1 changed", warnings[0][1])

    def test_missing_po_warns(self):
        r = self.repo(); r.po.unlink()
        errors, warnings, _ = r.run(["m/lang/ru_RU.mo"])
        self.assertEqual((errors, len(warnings)), ([], 1))

    def test_nested_lc_messages_layout_pairs_with_lang_po_dir(self):
        r = self.repo(); (r.root / "m/lang/po").mkdir(); (r.root / "m/lang/mo/ru/LC_MESSAGES").mkdir(parents=True)
        (r.root / "m/lang/po/ru.po").write_text(PO)
        subprocess.run(["msgfmt", "-o", r.root / "m/lang/mo/ru/LC_MESSAGES/ru.mo", r.root / "m/lang/po/ru.po"], check=True)
        self.assertEqual(r.run(["m/lang/mo/ru/LC_MESSAGES/ru.mo"])[:2], ([], []))

    def test_parse_accepts_big_endian(self):
        r = self.repo(); subprocess.run(["msgfmt", "--endianness=big", "-o", r.mo, r.po], check=True)
        self.assertEqual(parse_mo(r.mo.read_bytes())["hi"], "привет")


if __name__ == "__main__": unittest.main()
