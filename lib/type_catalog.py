# -*- coding: utf-8 -*-
"""
Read Revit type catalogs (the ``<family>.txt`` next to a ``<family>.rfa``).

Pure Python, no Revit API: safe on any thread and testable on CPython.

Format (Autodesk "Create a Type Catalog"):

* comma-delimited text, same base name and folder as the .rfa
* line 1: an empty first cell, then ``Name##TYPE##UNITS`` per parameter
* following lines: the type name, then one value per header column
* a literal ``"`` is written as ``""``
"""
import codecs
import os

_CACHE = {}
_CACHE_MAX = 64


class TypeCatalog(object):
    """Parsed catalog: header columns and one row per type."""

    def __init__(self, path, columns, rows):
        self.path = path
        # [{"name": u"Width", "kind": u"LENGTH", "unit": u"INCHES"}, ...]
        self.columns = columns
        # [(u"36\" x 80\"", [u"36", u"80", ...]), ...] in file order
        self.rows = rows

    @property
    def type_names(self):
        return [name for name, _values in self.rows]

    def __len__(self):
        return len(self.rows)


def catalog_path_for(rfa_path):
    """Return the type catalog path for *rfa_path*, or None if there is none."""
    if not rfa_path:
        return None
    candidate = os.path.splitext(rfa_path)[0] + u".txt"
    try:
        if os.path.isfile(candidate):
            return candidate
    except Exception:
        pass
    return None


def has_catalog(rfa_path):
    return catalog_path_for(rfa_path) is not None


def load_for(rfa_path):
    """Parse the catalog next to *rfa_path*; None if missing or unreadable.

    Results are cached by (path, modified time, size).
    """
    path = catalog_path_for(rfa_path)
    if path is None:
        return None
    try:
        stat = os.stat(path)
        key = (path, stat.st_mtime, stat.st_size)
    except Exception:
        key = None
    if key is not None and key in _CACHE:
        return _CACHE[key]
    try:
        catalog = parse_file(path)
    except Exception:
        return None
    if key is not None:
        if len(_CACHE) >= _CACHE_MAX:
            _CACHE.clear()
        _CACHE[key] = catalog
    return catalog


def parse_file(path):
    with open(path, "rb") as stream:
        data = stream.read()
    return parse_text(decode_bytes(data), path=path)


def decode_bytes(data):
    """Decode catalog bytes: BOM first, then UTF-16 sniffing, UTF-8, cp1252."""
    if data.startswith(codecs.BOM_UTF8):
        return data[len(codecs.BOM_UTF8):].decode("utf-8", "replace")
    if data.startswith(codecs.BOM_UTF16_LE):
        return data[2:].decode("utf-16-le", "replace")
    if data.startswith(codecs.BOM_UTF16_BE):
        return data[2:].decode("utf-16-be", "replace")
    sample = data[:200]
    if sample and sample.count(b"\x00") > len(sample) // 4:
        # No BOM but mostly NUL bytes: UTF-16 without a BOM.
        odd_nuls = sample[1::2].count(b"\x00")
        even_nuls = sample[0::2].count(b"\x00")
        enc = "utf-16-le" if odd_nuls >= even_nuls else "utf-16-be"
        return data.decode(enc, "replace")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("cp1252", "replace")


def split_row(line):
    """Split one comma-delimited line, honouring quotes and ``""`` escapes."""
    fields = []
    buf = []
    in_quotes = False
    i = 0
    n = len(line)
    while i < n:
        ch = line[i]
        if ch == u'"':
            if i + 1 < n and line[i + 1] == u'"':
                buf.append(u'"')
                i += 2
                continue
            if in_quotes:
                in_quotes = False
            elif not u"".join(buf).strip():
                in_quotes = True
                buf = []
            else:
                buf.append(ch)
        elif ch == u"," and not in_quotes:
            fields.append(u"".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
        i += 1
    fields.append(u"".join(buf).strip())
    return fields


def _parse_header_cell(cell):
    parts = cell.split(u"##")
    name = parts[0].strip()
    kind = parts[1].strip().upper() if len(parts) > 1 else u""
    unit = parts[2].strip().upper() if len(parts) > 2 else u""
    return {"name": name, "kind": kind, "unit": unit}


def parse_text(text, path=u""):
    lines = [line for line in text.replace(u"\r\n", u"\n").replace(u"\r", u"\n").split(u"\n")]
    lines = [line for line in lines if line.strip()]
    if not lines:
        return TypeCatalog(path, [], [])
    header = split_row(lines[0])
    columns = [_parse_header_cell(cell) for cell in header[1:]]
    # Drop trailing empty header cells (trailing commas from spreadsheets).
    while columns and not columns[-1]["name"]:
        columns.pop()
    width = len(columns)
    rows = []
    seen = set()
    for line in lines[1:]:
        cells = split_row(line)
        name = cells[0] if cells else u""
        if not name or name in seen:
            continue
        seen.add(name)
        values = cells[1:1 + width]
        values += [u""] * (width - len(values))
        rows.append((name, values))
    return TypeCatalog(path, columns, rows)


def column_header(column):
    """Display text for a column, e.g. ``Width (in)``."""
    unit = _UNIT_LABELS.get(column.get("unit") or u"", u"")
    name = column.get("name") or u""
    return u"{} ({})".format(name, unit) if unit else name


_UNIT_LABELS = {
    u"FEET": u"ft",
    u"INCHES": u"in",
    u"MILLIMETERS": u"mm",
    u"CENTIMETERS": u"cm",
    u"METERS": u"m",
    u"SQUARE_FEET": u"ft²",
    u"SQUARE_METERS": u"m²",
    u"CUBIC_FEET": u"ft³",
    u"CUBIC_METERS": u"m³",
    u"DEGREES": u"°",
    u"SLOPE_DEGREES": u"°",
}
