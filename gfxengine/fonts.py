"""Font files' names, read from their 'name' table (TrueType / OpenType;
WOFF2 is compressed, so it's named after its file instead).

A font is used by its PostScript name (e.g. "Gotham-Bold"), which is also
what Photoshop records for text layers, so imported PSDs pick up the right
font as soon as its file is in the assets.
"""

import os
import struct

FONT_EXTS = (".ttf", ".otf", ".woff", ".woff2")


def _name_table(data):
    if data[:4] == b"wOFF":
        return _woff_name_table(data)
    if data[:4] == b"ttcf":
        offset = struct.unpack(">I", data[12:16])[0]   # the first font in a collection
    else:
        offset = 0
    num_tables = struct.unpack(">H", data[offset + 4:offset + 6])[0]
    for i in range(num_tables):
        rec = offset + 12 + 16 * i
        tag, _, table_off, length = struct.unpack(">4sIII", data[rec:rec + 16])
        if tag == b"name":
            return data[table_off:table_off + length]
    return None


def _woff_name_table(data):
    import zlib
    num_tables = struct.unpack(">H", data[12:14])[0]
    for i in range(num_tables):
        rec = 44 + 20 * i
        tag, off, comp_len, orig_len, _ = struct.unpack(">4sIIII", data[rec:rec + 20])
        if tag == b"name":
            raw = data[off:off + comp_len]
            return zlib.decompress(raw) if comp_len < orig_len else raw
    return None


def names(path):
    """{"postscript", "family", "style"} for a font file (from its file name if unreadable)."""
    fallback = os.path.splitext(os.path.basename(path))[0]
    out = {"postscript": fallback, "family": fallback, "style": ""}
    try:
        with open(path, "rb") as f:
            data = f.read()
        table = _name_table(data)
        if not table:
            return out
        count, string_off = struct.unpack(">HH", table[2:6])
        found = {}
        for i in range(count):
            platform, encoding, lang, name_id, length, off = struct.unpack(">HHHHHH", table[6 + 12 * i:18 + 12 * i])
            if name_id not in (1, 2, 4, 6, 16, 17):
                continue
            raw = table[string_off + off:string_off + off + length]
            if platform == 3 or platform == 0:
                text = raw.decode("utf-16-be", "replace")
                rank = 2 if platform == 3 and lang == 0x409 else 1
            elif platform == 1:
                text = raw.decode("mac_roman", "replace")
                rank = 0
            else:
                continue
            if name_id not in found or rank > found[name_id][0]:
                found[name_id] = (rank, text.strip())
        get = lambda n: found.get(n, (0, ""))[1]
        out["postscript"] = get(6) or get(4).replace(" ", "-") or fallback
        out["family"] = get(16) or get(1) or fallback
        out["style"] = get(17) or get(2)
    except (OSError, struct.error, ValueError):
        pass
    return out


def is_font(name):
    return name.lower().endswith(FONT_EXTS)
