# -*- coding: utf-8 -*-
import codecs
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LIB = os.path.join(ROOT, "lib")
if LIB not in sys.path:
    sys.path.insert(0, LIB)

import type_catalog  # noqa: E402

SAMPLE = (
    u",Width##LENGTH##INCHES,Height##LENGTH##INCHES,Manufacturer##OTHER##\n"
    u"36\"\" x 80\"\",36,80,Acme\n"
    u"\"Pair, 72\"\" x 84\"\"\",72,84,\"Acme, Inc.\"\n"
    u"\n"
    u"Short row,30\n"
)


class TypeCatalogTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _write(self, name, data):
        path = os.path.join(self.dir, name)
        with open(path, "wb") as stream:
            stream.write(data)
        return path

    def test_parses_header_rows_quotes_and_short_rows(self):
        cat = type_catalog.parse_text(SAMPLE)
        self.assertEqual(
            [c["name"] for c in cat.columns],
            ["Width", "Height", "Manufacturer"])
        self.assertEqual(cat.columns[0]["kind"], "LENGTH")
        self.assertEqual(cat.columns[0]["unit"], "INCHES")
        self.assertEqual(cat.columns[2]["unit"], "")
        self.assertEqual(cat.type_names,
                         ['36" x 80"', 'Pair, 72" x 84"', "Short row"])
        self.assertEqual(cat.rows[1][1], ["72", "84", "Acme, Inc."])
        self.assertEqual(cat.rows[2][1], ["30", "", ""])

    def test_finds_sibling_txt_and_decodes_utf16(self):
        rfa = self._write("Door.rfa", b"")
        self.assertIsNone(type_catalog.load_for(rfa))
        self._write("Door.txt", codecs.BOM_UTF16_LE + SAMPLE.encode("utf-16-le"))
        cat = type_catalog.load_for(rfa)
        self.assertEqual(len(cat), 3)
        self.assertTrue(type_catalog.has_catalog(rfa))

    def test_decodes_cp1252_and_bomless_utf16(self):
        text = u",Note##OTHER##\nTürblatt,café\n"
        self.assertEqual(
            type_catalog.parse_text(
                type_catalog.decode_bytes(text.encode("cp1252"))).rows[0],
            (u"Türblatt", [u"café"]))
        self.assertEqual(
            type_catalog.decode_bytes(text.encode("utf-16-le")), text)

    def test_header_label_uses_short_units(self):
        self.assertEqual(
            type_catalog.column_header({"name": "Width", "unit": "INCHES"}),
            "Width (in)")
        self.assertEqual(
            type_catalog.column_header({"name": "Model", "unit": ""}), "Model")

    def test_duplicate_type_names_keep_first(self):
        cat = type_catalog.parse_text(u",A##OTHER##\nT1,1\nT1,2\n")
        self.assertEqual(cat.rows, [(u"T1", [u"1"])])


if __name__ == "__main__":
    unittest.main()
