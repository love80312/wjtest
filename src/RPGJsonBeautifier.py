#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RPGJsonBeautifier - lossless RPG Maker MV/MZ JSON formatter for WinMerge.

The layout follows the standalone "RPG JSON 美化工具" (RPGgameJSON_9.html):
compact "tight" separators (``[0,0,0]``, ``"key":value``), Tab indentation,
merged closing brackets (``}]}``), "snug" openings and merged empty entries.
Every layout switch can be changed in ``RPGJsonBeautifier.ini`` (next to this
script) or on the command line.

Safety guarantees:
  * only whitespace outside JSON strings is regenerated; number spellings,
    string escapes, key order and duplicate keys are kept verbatim;
  * the result is verified against the input before it is written;
  * the input file is never modified.

Speed notes (WinMerge starts this script once per compared file):
  * only ``json``, ``os``, ``re``, ``sys`` and ``collections`` are imported at start-up
    (argparse, dataclasses, pathlib, tempfile, configparser cost ~25 ms on their own);
  * numeric arrays and "flat" objects (event commands, actors, items...) are parsed with a
    single regular-expression match instead of one match per token;
  * the integrity check uses str.replace and the C json scanner instead of four regex passes.

Standard library only; Python 3.10+.
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import namedtuple

# --------------------------------------------------------------------------
# Errors, options
# --------------------------------------------------------------------------


class JsonFormatError(ValueError):
    pass


# Layout switches. Defaults match the HTML tool's defaults.
#   hug          merge closers that directly follow another closer: }\n] -> }]
#   tight        no space after "," and ":"   ->  [0,0,0]  "k":v
#   wrap         wrap very long numeric arrays at WRAP_WIDTH columns
#   tab          indent with Tab instead of two spaces
#   snug         "{" joins its first entry; "[" joins a leading null; [[1,2]] and [true,false] stay on one line
#   merge_empty  consecutive empty-valued entries (and adjacent "" in arrays) share a line
Options = namedtuple(
    "Options",
    ("hug", "tight", "wrap", "tab", "snug", "merge_empty"),
    defaults=(True, True, False, True, True, True),
)

# Plain look: two spaces, ", " and ": " and every optional layout feature off (the rules that have no switch still apply).
LEGACY = Options(hug=False, tight=False, wrap=False, tab=False, snug=False, merge_empty=False)

WRAP_WIDTH = 100      # numeric-array wrap column
COMPACT_WIDTH = 100   # widest merged line of empty entries (a Tab counts as 2 columns)
MAX_DEPTH = 200       # RPG Maker data is shallow; this only guards against pathological input


def _decode(raw: str) -> str:
    """Decoded value of a raw JSON string token (only needed for escaped strings and keys)."""
    return json.loads(raw)


# --------------------------------------------------------------------------
# Lossless parser. Node = str (raw scalar token) | Array | Obj
# --------------------------------------------------------------------------


class Array:
    __slots__ = ("items", "scalars", "numeric")

    def __init__(self, items: list | None = None, scalars: bool | None = None, numeric: bool = False) -> None:
        self.items = [] if items is None else items
        self.scalars = scalars    # every item is a scalar token; None until finish()
        self.numeric = numeric    # non-empty and every item is a number or null

    def finish(self) -> None:
        scalars = numeric = True
        for x in self.items:
            if type(x) is not str:
                scalars = numeric = False
                break
            if numeric and not (x[0] in "-0123456789" or x == "null"):
                numeric = False
        self.scalars = scalars
        self.numeric = numeric and bool(self.items)


class Obj:
    __slots__ = ("entries", "all_empty", "has_code", "flat", "all_scalar")

    def __init__(self) -> None:
        # A list of (raw key token, node): JSON duplicate keys and order must survive.
        self.entries: list[tuple[str, Node]] = []
        self.all_empty: bool | None = None    # None until finish()
        self.has_code = False                 # has a "code" key (RPG Maker event command)
        self.flat = True                      # every value is a scalar or an array of scalars
        self.all_scalar = True                # every value is a scalar

    def finish(self) -> None:
        all_empty, has_code, flat, all_scalar = True, False, True, True
        for k, v in self.entries:
            t = type(v)
            if t is str:
                if v != "null" and v != '""':
                    all_empty = False
            else:
                all_scalar = False
                if t is Array:
                    if v.items:
                        all_empty = False
                    if not v.scalars:
                        flat = False
                else:
                    flat = False
                    if v.entries:
                        all_empty = False
            if not has_code and (k == '"code"' or ("\\" in k and _decode(k) == "code")):
                has_code = True
        self.all_empty, self.has_code, self.flat, self.all_scalar = all_empty, has_code, flat, all_scalar


Node = str | Array | Obj

_WS = r"[ \t\r\n]*"
_STRING = r'"[^"\\\x00-\x1f]*(?:\\(?:["\\/bfnrt]|u[0-9A-Fa-f]{4})[^"\\\x00-\x1f]*)*"'
_NUMBER = r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?"
_LITERAL = r"true|false|null"
_PUNCT = r"[\[\]{},:]"
_SCALAR = rf"(?:{_STRING}|{_NUMBER}|{_LITERAL})"

# group 1 string, 2 number, 3 literal, 4 punctuation (leading whitespace is skipped)
_TOKEN = re.compile(rf"{_WS}(?:({_STRING})|({_NUMBER})|({_LITERAL})|({_PUNCT}))")

# Fast paths. "Flat" = scalars and arrays of at most 64 scalars, objects of at most 256 entries
# (bigger ones take the token loop: a regex repeat keeps backtracking state per iteration, i.e. memory). In each loop the separator is
# "a comma followed by the start of another item" or "directly the closer", which rejects trailing
# commas and missing commas without repeating the item pattern.
_FLAT_ITEM = re.compile(rf"{_WS}(?:{_NUMBER}|null){_WS}")
_NOT_FLAT = re.compile(r'[\[{"]')
_FLAT_ARRAY = rf'\[{_WS}(?:{_SCALAR}{_WS}(?:,{_WS}(?=["\-0-9tfn])|(?=\]))){{0,64}}\]'
_FLAT_VALUE = rf"(?:{_SCALAR}|{_FLAT_ARRAY})"
_FLAT_OBJECT = re.compile(
    rf'\{{{_WS}(?:{_STRING}{_WS}:{_WS}{_FLAT_VALUE}{_WS}(?:,{_WS}(?=")|(?=\}}))){{0,256}}\}}'
)
_ENTRY = re.compile(rf"({_STRING}){_WS}:{_WS}({_FLAT_VALUE})")
_SCALAR_TOKEN = re.compile(_SCALAR)

_TRAILING_WS = re.compile(r"[ \t\r\n]*\Z")
_HEX4 = re.compile(r"[0-9A-Fa-f]{4}\Z")

_VALUE, _VALUE_OR_END, _KEY, _KEY_OR_END, _COLON, _COMMA_OR_END = range(6)


def _error(src: str, pos: int, message: str) -> JsonFormatError:
    line = src.count("\n", 0, pos) + 1
    col = pos - (src.rfind("\n", 0, pos) + 1) + 1
    excerpt = src[max(0, pos - 20):pos + 20].replace("\r", "\\r").replace("\n", "\\n")
    return JsonFormatError(f"{message}（第 {line} 行，第 {col} 欄；附近內容: {excerpt!r}）")


def _string_error(src: str, pos: int) -> JsonFormatError:
    """Explain why the string starting at src[pos] is not a valid JSON string."""
    i, n = pos + 1, len(src)
    while i < n:
        c = src[i]
        if ord(c) < 0x20:
            return _error(src, i, "JSON 字串含有未跳脫的控制字元")
        if c == "\\":
            e = src[i + 1:i + 2]
            if e == "u":
                if not _HEX4.match(src, i + 2, i + 6):
                    return _error(src, i, "JSON 字串的 Unicode 跳脫序列無效")
                i += 6
                continue
            if e and e in '"\\/bfnrt':
                i += 2
                continue
            return _error(src, i, "JSON 字串的跳脫序列無效")
        i += 1
    return _error(src, pos, "JSON 字串未結束")


def _lex_error(src: str, pos: int) -> JsonFormatError:
    n = len(src)
    while pos < n and src[pos] in " \t\r\n":
        pos += 1
    if pos >= n:
        return _error(src, n, "JSON 內容意外結束")
    if src[pos] == '"':
        return _string_error(src, pos)
    return _error(src, pos, f"不合法的 JSON 內容「{src[pos]}」")


def _flat_numbers(src: str, pos: int) -> tuple[list[str], int] | None:
    """Fast path for ``[1,0,null,...]`` (map tile data): returns (raw items, index after "]")."""
    end = src.find("]", pos)
    if end == -1 or _NOT_FLAT.search(src, pos, end):
        return None
    parts = src[pos:end].split(",")
    if not all(map(_FLAT_ITEM.fullmatch, parts)):   # strict: rejects 01, 1., 1 2, 1,,2, ...
        return None
    return [p.strip(" \t\r\n") for p in parts], end + 1


def _flat_object(src: str, start: int) -> tuple[Obj, int] | None:
    """Fast path for an object whose values are scalars or short scalar arrays, e.g. an event
    command ``{"code":401,"indent":0,"parameters":["text"]}``: one match instead of ~17 tokens."""
    m = _FLAT_OBJECT.match(src, start)
    if m is None:
        return None
    obj = Obj()
    entries = obj.entries
    for key, raw in _ENTRY.findall(src, start, m.end()):      # pos/endpos: no substring copy
        if raw[0] == "[":
            arr = Array(_SCALAR_TOKEN.findall(raw, 1, len(raw) - 1))
            arr.finish()
            entries.append((key, arr))
        else:
            entries.append((key, raw))
    obj.finish()
    return obj, m.end()


def parse_json(src: str) -> Node:
    """Parse JSON into a tree of raw tokens. Iterative, so nesting never hits the recursion limit."""
    if not src.strip(" \t\r\n"):
        raise JsonFormatError("JSON 內容是空的")

    match_token = _TOKEN.match
    stack: list[Array | Obj] = []     # open containers
    keys: list[str] = []              # keys[i] = key waiting for its value in stack[i] (objects only)
    pos = 0
    state = _VALUE

    while True:
        m = match_token(src, pos)
        if m is None:
            raise _lex_error(src, pos)
        kind = m.lastindex
        tok = m.group(kind)
        pos = m.end()

        if state == _COMMA_OR_END:
            top = stack[-1]
            is_array = type(top) is Array
            if kind != 4 or (tok != "," and tok != ("]" if is_array else "}")):
                raise _error(src, m.start(kind), "陣列項目之間預期逗號" if is_array else "物件項目之間預期逗號")
            if tok == ",":
                state = _VALUE if is_array else _KEY
                continue
            value: Node = stack.pop()
            keys.pop()

        elif state == _VALUE or state == _VALUE_OR_END:
            if kind != 4:
                value = tok                               # string / number / literal
            elif tok == "[" or tok == "{":
                flat = _flat_numbers(src, pos) if tok == "[" else _flat_object(src, pos - 1)
                if flat is None:
                    if len(stack) >= MAX_DEPTH:
                        raise _error(src, m.start(kind), f"JSON 巢狀超過 {MAX_DEPTH} 層")
                    stack.append(Array() if tok == "[" else Obj())
                    keys.append("")
                    state = _VALUE_OR_END if tok == "[" else _KEY_OR_END
                    continue
                if tok == "[":
                    value, pos = Array(flat[0], True, True), flat[1]
                else:
                    value, pos = flat
            elif tok == "]" and state == _VALUE_OR_END:
                value = stack.pop()                       # empty array
                keys.pop()
            else:
                raise _error(src, m.start(kind), "JSON 陣列不允許尾隨逗號" if tok == "]" else "預期 JSON 值")

        elif state == _COLON:
            if kind != 4 or tok != ":":
                raise _error(src, m.start(kind), "物件鍵後面預期冒號")
            state = _VALUE
            continue

        else:  # _KEY / _KEY_OR_END
            if kind == 1:
                keys[-1] = tok
                state = _COLON
                continue
            if state == _KEY_OR_END and tok == "}":
                value = stack.pop()                       # empty object
                keys.pop()
            else:
                raise _error(src, m.start(kind), "JSON 物件不允許尾隨逗號" if tok == "}" else "物件中預期字串鍵名")

        # A complete value: classify finished containers, then attach it to its parent.
        t = type(value)
        if t is Array:
            if value.scalars is None:
                value.finish()
        elif t is Obj and value.all_empty is None:
            value.finish()
        if not stack:
            break
        top = stack[-1]
        if type(top) is Array:
            top.items.append(value)
        else:
            top.entries.append((keys[-1], value))
        state = _COMMA_OR_END

    if not _TRAILING_WS.match(src, pos):
        while src[pos] in " \t\r\n":
            pos += 1
        raise _error(src, pos, "JSON 根值之後有多餘內容")
    return value


# --------------------------------------------------------------------------
# Layout (ported rule-for-rule from RPGgameJSON_9.html so both tools agree)
# --------------------------------------------------------------------------

_SHORT_ASCII = re.compile(r"[A-Za-z0-9_]{1,9}\Z")


def _is_short_ascii(node: Node) -> bool:
    if type(node) is not str or node[0] != '"':
        return False
    text = node[1:-1] if "\\" not in node else _decode(node)
    return _SHORT_ASCII.match(text) is not None


def _fits(text: str, pad_w: int) -> bool:
    # visual width >= len(text), so the cheap length test rules out long text (e.g. notes) early
    return len(text) + pad_w <= COMPACT_WIDTH and _visual_width(text) + pad_w <= COMPACT_WIDTH


class _Formatter:
    def __init__(self, opts: Options) -> None:
        self.opts = opts
        self.comma = "," if opts.tight else ", "
        self.colon = ":" if opts.tight else ": "
        self.unit = "\t" if opts.tab else "  "
        self._pads: dict[int, str] = {}

    # -- entry point -------------------------------------------------------

    def format(self, root: Node) -> str:
        return self._tidy(self._fmt(root, 0))

    # -- tree layout -------------------------------------------------------

    def _pad(self, indent: int) -> str:
        pad = self._pads.get(indent)
        if pad is None:
            pad = self._pads[indent] = self.unit * indent
        return pad

    def _inline(self, node: Node) -> str:
        if type(node) is str:
            return node
        if type(node) is Array:
            if node.scalars:
                return "[" + self.comma.join(node.items) + "]"
            return "[" + self.comma.join(self._inline(x) for x in node.items) + "]"
        return "{" + self.comma.join(k + self.colon + self._inline(v) for k, v in node.entries) + "}"

    def _numeric_inline(self, node: Node) -> str | None:
        """"[1,0,0]" or a single-element wrapper around it "[[1,0,0]]" (any depth); else None."""
        if type(node) is not Array or not node.items:
            return None
        if node.numeric:
            return "[" + self.comma.join(node.items) + "]"
        if len(node.items) == 1:
            inner = self._numeric_inline(node.items[0])
            return None if inner is None else "[" + inner + "]"
        return None

    def _close(self, opener: str, parts: list[str], closer: str, pad: str) -> str:
        # When the last child is itself a multi-line container its closer already ends a line,
        # so the parent's closer is appended right after it instead of starting a new line.
        last = parts[-1]
        hugs = self.opts.hug and last.endswith(("]", "}")) and "\n" in last
        return opener + "\n" + ",\n".join(parts) + ("" if hugs else "\n" + pad) + closer

    def _fmt(self, node: Node, indent: int) -> str:
        if type(node) is str:
            return node
        if type(node) is Array:
            return self._fmt_array(node, indent)
        return self._fmt_object(node, indent)

    def _fmt_array(self, node: Array, indent: int) -> str:
        items = node.items
        if not items:
            return "[]"
        pad_w = indent * 2          # visual width (Tab = 2 columns): wrapping is identical for Tab and spaces

        # Numeric arrays (including null) stay on one line, optionally wrapped when very long.
        if node.numeric:
            one = "[" + self.comma.join(items) + "]"
            if not self.opts.wrap or len(one) + pad_w <= WRAP_WIDTH:
                return one
            return self._wrap_numbers(items, indent, pad_w)

        # A single wrapper around a numeric array stays on one line when it fits.
        if self.opts.snug and len(items) == 1:
            one = self._numeric_inline(node)
            if one is not None and len(one) + pad_w <= WRAP_WIDTH:
                return one

        # Short ASCII alphanumeric string arrays stay on one line.
        if node.scalars and all(map(_is_short_ascii, items)):
            return "[" + self.comma.join(items) + "]"

        # Short boolean arrays stay on one line when they fit.
        if self.opts.snug and node.scalars and all(x == "true" or x == "false" for x in items):
            one = "[" + self.comma.join(items) + "]"
            if _fits(one, pad_w):
                return one

        # Other arrays expand; consecutive nulls (and, with merge_empty, empty strings) are grouped.
        pad1 = self._pad(indent + 1)
        merge = self.opts.merge_empty
        parts: list[str] = []
        i, n = 0, len(items)
        while i < n:
            raw = items[i]
            if raw == "null" or (merge and raw == '""'):
                j = i + 1
                while j < n and items[j] == raw:
                    j += 1
                parts.append(pad1 + self.comma.join([raw] * (j - i)))
                i = j
            else:
                parts.append(pad1 + self._fmt(items[i], indent + 1))
                i += 1
        return self._close("[", parts, "]", self._pad(indent))

    def _wrap_numbers(self, items: list[str], indent: int, pad_w: int) -> str:
        pad, pad1, comma = self._pad(indent), self._pad(indent + 1), self.comma
        lines: list[str] = []
        cur = ""
        for raw in items:
            if cur and pad_w + 2 + len(cur) + len(comma) + len(raw) > WRAP_WIDTH:
                lines.append(pad1 + cur + ",")
                cur = raw
            else:
                cur = cur + comma + raw if cur else raw
        lines.append(pad1 + cur)
        return "[\n" + "\n".join(lines) + "\n" + pad + "]"

    def _fmt_object(self, node: Obj, indent: int) -> str:
        entries = node.entries
        if not entries:
            return "{}"
        # Flags were computed once by Obj.finish() while parsing.
        if node.all_empty:
            return self._inline(node)
        # RPG MV/MZ command objects: has a "code" key and every value is a scalar / scalar array.
        if node.has_code and node.flat:
            return self._inline(node)
        # Short objects whose direct values are all scalars stay on one line.
        if node.all_scalar:
            one = self._inline(node)
            if _fits(one, indent * 2):
                return one
        pad1 = self._pad(indent + 1)
        colon = self.colon
        parts = [pad1 + k + colon + self._fmt(v, indent + 1) for k, v in entries]
        return self._close("{", parts, "}", self._pad(indent))

    # -- whitespace-only tidying of the finished text ----------------------

    def _tidy(self, text: str) -> str:
        if not (self.opts.merge_empty or self.opts.snug):
            return text
        lines = text.split("\n")      # JSON strings never contain raw newlines
        if self.opts.merge_empty:
            lines = self._merge_empty(lines)
        if self.opts.snug:
            lines = _snug_openings(lines)
        return "\n".join(lines)

    def _merge_empty(self, lines: list[str]) -> list[str]:
        """Consecutive empty-valued entries ("a":"", "b":[], "c":null, "d":{}) share a line."""
        sep = " " if len(self.comma) > 1 else ""
        out: list[str] = []
        i, n = 0, len(lines)
        while i < n:
            first = _empty_entry(lines[i])
            if first is None:
                out.append(lines[i])
                i += 1
                continue
            indent = first.group(1)
            items: list[str] = []
            j = i
            while j < n:
                m = _empty_entry(lines[j])
                if m is None or m.group(1) != indent:
                    break
                items.append(m.group(2))
                j += 1
                if not m.group(2).endswith(","):      # no trailing comma = last entry of its object
                    break
            base = _visual_width(indent)
            row, row_w = "", 0
            for item in items:
                w = _visual_width(item)
                if not row:
                    row, row_w = item, base + w
                elif row_w + len(sep) + w > COMPACT_WIDTH:
                    out.append(indent + row)
                    row, row_w = item, base + w
                else:
                    row += sep + item
                    row_w += len(sep) + w
            out.append(indent + row)
            i = j
        return out


_EMPTY_ENTRY = re.compile(r'(\s*)("(?:[^"\\]|\\.)*"\s*:\s*(?:""|null|\[\]|\{\}),?)\s*\Z')
_EMPTY_TAILS = ('""', "null", "[]", "{}")
_NULL_START = re.compile(r"\s*null\b")


def _empty_entry(line: str) -> re.Match[str] | None:
    body = line[:-1] if line.endswith(",") else line
    if not body.endswith(_EMPTY_TAILS):      # cheap pre-check; our own output has no trailing blanks
        return None
    return _EMPTY_ENTRY.match(line)


def _visual_width(s: str) -> int:
    return sum(2 if ch == "\t" or ord(ch) >= 0x1100 else 1 for ch in s)


def _snug_openings(lines: list[str]) -> list[str]:
    """A lone "{" joins its first entry; an array's "[" joins a leading null."""
    out: list[str] = []
    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        nxt = lines[i + 1] if i + 1 < n else None
        if nxt is not None:
            if line.strip() == "{":
                third = lines[i + 2] if i + 2 < n else None
                # a one-entry object ({ / "k": v / }) collapses to one line instead of leaving a lone closer
                if third is not None and third.lstrip().startswith("}") and \
                        len(third) - len(third.lstrip()) == len(line) - len(line.lstrip()):
                    out.append(line + nxt.lstrip() + third.lstrip())
                    i += 3
                else:
                    out.append(line + nxt.lstrip())
                    i += 2
                continue
            if line.endswith("[") and _NULL_START.match(nxt):
                out.append(line + nxt.lstrip())
                i += 2
                continue
        out.append(line)
        i += 1
    return out


# --------------------------------------------------------------------------
# Integrity gate
# --------------------------------------------------------------------------

_STRINGS = re.compile(r'"[^"\\]*(?:\\.[^"\\]*)*"')


def _drop_ws(text: str) -> str:
    # Four str.replace calls run at memory speed (a regex pass is ~10x slower).
    return text.replace(" ", "").replace("\t", "").replace("\r", "").replace("\n", "")


def verify_lossless(source: str, output: str) -> None:
    """Raise unless `output` is `source` with only whitespace between tokens changed.

    1. identical once all JSON whitespace is removed (same characters, same order, so no value,
       number spelling, escape, key or bracket was touched);
    2. `output` is valid JSON (the C scanner; nothing was inserted inside a number or literal);
    3. every string token is identical including the whitespace inside it.
    Together they imply the token sequences are equal. `source` was already validated by parse_json.
    """
    if _drop_ws(source) != _drop_ws(output):
        raise JsonFormatError("完整性檢查失敗：輸出內容不只是排版空白差異")
    try:
        # len() as number hook: validity only, skips int()/float() conversion of every number
        json.loads(output, parse_int=len, parse_float=len)
    except (ValueError, RecursionError) as exc:
        raise JsonFormatError("完整性檢查失敗：輸出不是有效的 JSON") from exc
    if _STRINGS.findall(source) != _STRINGS.findall(output):
        raise JsonFormatError("完整性檢查失敗：字串內容（含內部空白）與原文不同")


# --------------------------------------------------------------------------
# Public API, config, CLI
# --------------------------------------------------------------------------


def beautify_text(source: str, options: Options | None = None) -> str:
    opts = options or Options()
    try:
        formatted = _Formatter(opts).format(parse_json(source))
    except RecursionError as exc:       # defensive: MAX_DEPTH normally triggers first
        raise JsonFormatError("JSON 巢狀太深，無法排版") from exc
    verify_lossless(source, formatted)
    return formatted + "\n"


def read_text(path: str | os.PathLike) -> str:
    with open(path, "rb") as fh:
        data = fh.read()
    # JSON is normally UTF-8; support UTF-8 BOM and UTF-16 BOM as well.
    if data.startswith(b"\xef\xbb\xbf"):
        return data.decode("utf-8-sig")
    if data.startswith(b"\xff\xfe") or data.startswith(b"\xfe\xff"):
        return data.decode("utf-16")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise JsonFormatError(f"無法以 UTF-8 讀取檔案：{exc}") from exc


def _log_path() -> str | None:
    override = os.environ.get("RPGJSONBEAUTIFIER_LOG")    # empty string disables logging
    if override is not None:
        return override or None
    for name in ("TEMP", "TMP", "TMPDIR"):
        folder = os.environ.get(name)
        if folder:
            return os.path.join(folder, "RPGJsonBeautifier.log")
    return os.path.join("C:\\Windows\\Temp" if os.name == "nt" else "/tmp", "RPGJsonBeautifier.log")


def log(message: str) -> None:
    """Append to %TEMP%\\RPGJsonBeautifier.log. WinMerge hides this script's stderr, so failures land here."""
    path = _log_path()
    if path is None:
        return
    try:
        import time
        if os.path.exists(path) and os.path.getsize(path) > 256 * 1024:
            os.remove(path)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n")
    except OSError:
        pass


_BOOLEANS = {"1": True, "yes": True, "true": True, "on": True, "0": False, "no": False, "false": False, "off": False}


def _read_ini_section(path: str, section: str) -> dict[str, str]:
    """Minimal INI reader: `[section]`, `key = value`, full-line and inline (" ;" / " #") comments."""
    with open(path, "rb") as fh:
        text = fh.read().decode("utf-8-sig")
    values: dict[str, str] = {}
    current = ""
    for line in text.splitlines():
        line = line.strip()
        if not line or line[0] in ";#":
            continue
        if line[0] == "[" and line[-1] == "]":
            current = line[1:-1].strip().lower()
            continue
        key, sep, value = line.partition("=")
        if current != section or not sep:
            continue
        for i in range(1, len(value)):
            if value[i] in ";#" and value[i - 1].isspace():
                value = value[:i]
                break
        values[key.strip().lower()] = value.strip()
    return values


def load_options(config_path: str | os.PathLike | None = None) -> Options:
    """Defaults, overridden by the [format] section of the .ini file next to this script."""
    path = os.fspath(config_path) if config_path else os.path.splitext(os.path.realpath(__file__))[0] + ".ini"
    chosen: dict[str, bool] = {}
    if os.path.isfile(path):
        name = os.path.basename(path)
        try:
            raw = _read_ini_section(path, "format")
        except (OSError, UnicodeDecodeError) as exc:
            log(f"{name}: 無法讀取設定檔，已使用預設值（{exc}）")
            raw = {}
        for key in Options._fields:
            if key in raw:
                flag = _BOOLEANS.get(raw[key].lower())
                if flag is None:
                    log(f"{name}: [format] {key} 的值不是 true/false，已使用預設值")
                else:
                    chosen[key] = flag
    return Options(**chosen)


_USAGE = ("用法: RPGJsonBeautifier.py 來源.json 輸出.json [--config 設定檔] "
          + " ".join(f"[--[no-]{n.replace('_', '-')}]" for n in Options._fields))


def _parse_args(argv: list[str]) -> tuple[str, str, str | None, dict[str, bool]]:
    paths: list[str] = []
    overrides: dict[str, bool] = {}
    config: str | None = None
    it = iter(argv)
    for arg in it:
        if arg == "--config" or arg.startswith("--config="):
            config = arg[9:] if arg.startswith("--config=") else next(it, None)
            if not config:
                raise ValueError("--config 需要設定檔路徑")
        elif arg.startswith("--"):
            name, value = (arg[5:], False) if arg.startswith("--no-") else (arg[2:], True)
            name = name.replace("-", "_")
            if name not in Options._fields:
                raise ValueError(f"不認得的選項 {arg}")
            overrides[name] = value
        else:
            paths.append(arg)
    if len(paths) != 2:
        raise ValueError("需要兩個路徑：來源與輸出")
    return paths[0], paths[1], config, overrides


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if "-h" in argv or "--help" in argv:
        print(_USAGE)
        return 0
    try:
        input_path, output_path, config, overrides = _parse_args(argv)
    except ValueError as exc:
        print(f"RPGJsonBeautifier: {exc}\n{_USAGE}", file=sys.stderr)
        return 2

    src = os.path.normcase(os.path.realpath(input_path))
    dst = os.path.normcase(os.path.realpath(output_path))
    if src == dst:
        print("錯誤：來源與輸出路徑相同，為避免覆寫原始檔案已取消。", file=sys.stderr)
        return 2

    try:
        options = load_options(config)._replace(**overrides)
        formatted = beautify_text(read_text(input_path), options)
        folder = os.path.dirname(dst)
        if folder:
            os.makedirs(folder, exist_ok=True)
        # UTF-8 output without BOM and with LF newlines, for predictable WinMerge display.
        with open(output_path, "w", encoding="utf-8", newline="") as fh:
            fh.write(formatted)
        return 0
    except (OSError, JsonFormatError) as exc:
        print(f"RPGJsonBeautifier: {exc}", file=sys.stderr)
        log(f"{input_path}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
