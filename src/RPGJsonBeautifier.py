#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RPGJsonBeautifier - lossless JSON formatter for WinMerge integration.

This is the Python formatter core. It does not modify input files unless the
caller explicitly chooses the same path as input and output (not recommended).
It preserves original JSON string tokens, number tokens, object key order, and
duplicate object keys. Only whitespace outside JSON strings is regenerated.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Union


class JsonFormatError(ValueError):
    pass


@dataclass
class Scalar:
    raw: str
    kind: str  # "string", "number", "true", "false", "null"


@dataclass
class Array:
    items: list["Node"]


@dataclass
class Object:
    # Keep a list, not a dict: JSON duplicate keys and order must survive.
    items: list[tuple[str, "Node"]]


Node = Union[Scalar, Array, Object]

_NUMBER_RE = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?")
_SHORT_ASCII_RE = re.compile(r"[A-Za-z0-9_]{1,9}\Z")


class Parser:
    def __init__(self, source: str):
        self.s = source
        self.i = 0
        self.n = len(source)

    def error(self, message: str) -> JsonFormatError:
        start = max(0, self.i - 20)
        end = min(self.n, self.i + 20)
        excerpt = self.s[start:end].replace("\r", "\\r").replace("\n", "\\n")
        return JsonFormatError(f"{message} (字元位置 {self.i}; 附近內容: {excerpt!r})")

    def ws(self) -> None:
        while self.i < self.n and self.s[self.i] in " \t\r\n":
            self.i += 1

    def parse(self) -> Node:
        self.ws()
        if self.i >= self.n:
            raise self.error("JSON 內容是空的")
        node = self.value()
        self.ws()
        if self.i != self.n:
            raise self.error("JSON 根值之後有多餘內容")
        return node

    def value(self) -> Node:
        self.ws()
        if self.i >= self.n:
            raise self.error("預期 JSON 值")
        ch = self.s[self.i]
        if ch == "{":
            return self.object()
        if ch == "[":
            return self.array()
        if ch == '"':
            return Scalar(self.string_token(), "string")
        for literal, kind in (("true", "true"), ("false", "false"), ("null", "null")):
            if self.s.startswith(literal, self.i):
                self.i += len(literal)
                return Scalar(literal, kind)
        m = _NUMBER_RE.match(self.s, self.i)
        if m:
            raw = m.group(0)
            self.i = m.end()
            # Reject invalid continuations such as 01, 1abc, or a trailing decimal.
            if self.i < self.n and self.s[self.i] not in " \t\r\n,]}":
                raise self.error("數字後面有不合法字元")
            return Scalar(raw, "number")
        raise self.error("不合法的 JSON 值")

    def string_token(self) -> str:
        start = self.i
        self.i += 1  # opening quote
        while self.i < self.n:
            ch = self.s[self.i]
            if ch == '"':
                self.i += 1
                token = self.s[start:self.i]
                # Validate escape syntax and reject raw control characters.
                j = 1
                while j < len(token) - 1:
                    c = token[j]
                    if ord(c) < 0x20:
                        raise self.error("JSON 字串含有未跳脫的控制字元")
                    if c == "\\":
                        j += 1
                        if j >= len(token) - 1:
                            raise self.error("JSON 字串的跳脫序列不完整")
                        esc = token[j]
                        if esc == "u":
                            hexpart = token[j + 1:j + 5]
                            if len(hexpart) != 4 or not all(x in "0123456789abcdefABCDEF" for x in hexpart):
                                raise self.error("JSON 字串的 Unicode 跳脫序列無效")
                            j += 4
                        elif esc not in '"\\/bfnrt':
                            raise self.error("JSON 字串的跳脫序列無效")
                    j += 1
                return token
            if ord(ch) < 0x20:
                raise self.error("JSON 字串含有未跳脫的控制字元")
            if ch == "\\":
                self.i += 1
                if self.i >= self.n:
                    raise self.error("JSON 字串未結束")
            self.i += 1
        raise self.error("JSON 字串未結束")

    def array(self) -> Array:
        self.i += 1
        self.ws()
        items: list[Node] = []
        if self.i < self.n and self.s[self.i] == "]":
            self.i += 1
            return Array(items)
        while True:
            items.append(self.value())
            self.ws()
            if self.i >= self.n:
                raise self.error("陣列未結束")
            ch = self.s[self.i]
            if ch == "]":
                self.i += 1
                return Array(items)
            if ch != ",":
                raise self.error("陣列項目之間預期逗號")
            self.i += 1
            self.ws()
            if self.i < self.n and self.s[self.i] == "]":
                raise self.error("JSON 陣列不允許尾隨逗號")

    def object(self) -> Object:
        self.i += 1
        self.ws()
        items: list[tuple[str, Node]] = []
        if self.i < self.n and self.s[self.i] == "}":
            self.i += 1
            return Object(items)
        while True:
            self.ws()
            if self.i >= self.n or self.s[self.i] != '"':
                raise self.error("物件鍵必須是 JSON 字串")
            key = self.string_token()
            self.ws()
            if self.i >= self.n or self.s[self.i] != ":":
                raise self.error("物件鍵後面預期冒號")
            self.i += 1
            val = self.value()
            items.append((key, val))
            self.ws()
            if self.i >= self.n:
                raise self.error("物件未結束")
            ch = self.s[self.i]
            if ch == "}":
                self.i += 1
                return Object(items)
            if ch != ",":
                raise self.error("物件項目之間預期逗號")
            self.i += 1
            self.ws()
            if self.i < self.n and self.s[self.i] == "}":
                raise self.error("JSON 物件不允許尾隨逗號")


def is_empty(node: Node) -> bool:
    if isinstance(node, Scalar):
        return node.kind in ("null", "false") or (node.kind == "number" and is_zero_number(node.raw)) or (
            node.kind == "string" and decoded_string_is_empty(node.raw)
        )
    if isinstance(node, Array):
        return not node.items
    return not node.items


def is_zero_number(raw: str) -> bool:
    # JSON numeric literal can be checked without float conversion.
    try:
        from decimal import Decimal
        return Decimal(raw).is_zero()
    except Exception:
        return False


def decoded_string_is_empty(raw: str) -> bool:
    # JSON string "" is empty; escaped sequences are not empty strings.
    return raw == '""'


def is_scalar(node: Node) -> bool:
    return isinstance(node, Scalar)


def is_scalar_or_scalar_array(node: Node) -> bool:
    return is_scalar(node) or (isinstance(node, Array) and all(is_scalar(x) for x in node.items))


def inline_full(node: Node) -> str:
    if isinstance(node, Scalar):
        return node.raw
    if isinstance(node, Array):
        return "[" + ", ".join(inline_full(x) for x in node.items) + "]"
    return "{" + ", ".join(k + ": " + inline_full(v) for k, v in node.items) + "}"


def format_rpg(node: Node, indent: int = 0) -> str:
    pad = "  " * indent
    pad1 = "  " * (indent + 1)

    if isinstance(node, Scalar):
        return node.raw

    if isinstance(node, Array):
        if not node.items:
            return "[]"
        # Numeric arrays (including null) stay on one line; raw number spellings survive.
        if all(isinstance(x, Scalar) and x.kind in ("number", "null") for x in node.items):
            return "[" + ", ".join(x.raw for x in node.items) + "]"
        # Short ASCII alphanumeric string arrays stay on one line.
        if all(isinstance(x, Scalar) and x.kind == "string" and
               _SHORT_ASCII_RE.fullmatch(decode_simple_string(x.raw) or "") for x in node.items):
            return "[" + ", ".join(x.raw for x in node.items) + "]"

        lines: list[str] = []
        i = 0
        while i < len(node.items):
            item = node.items[i]
            if isinstance(item, Scalar) and item.kind == "null":
                j = i
                while j < len(node.items) and isinstance(node.items[j], Scalar) and node.items[j].kind == "null":
                    j += 1
                lines.append(pad1 + ", ".join("null" for _ in range(j - i)))
                i = j
            else:
                lines.append(pad1 + format_rpg(item, indent + 1))
                i += 1
        return "[\n" + ",\n".join(lines) + "\n" + pad + "]"

    if not node.items:
        return "{}"
    if all(is_empty(v) for _, v in node.items):
        return inline_full(node)
    # RPG MV/MZ command objects: own "code" property and all values scalar/scalar-array.
    if any(decode_simple_string(k) == "code" for k, _ in node.items) and all(
        is_scalar_or_scalar_array(v) for _, v in node.items
    ):
        return inline_full(node)

    return "{\n" + ",\n".join(
        pad1 + key + ": " + format_rpg(value, indent + 1)
        for key, value in node.items
    ) + "\n" + pad + "}"


def decode_simple_string(raw: str) -> str | None:
    # Used only for checking short string-array values and the "code" property.
    try:
        import json
        value = json.loads(raw)
        return value if isinstance(value, str) else None
    except Exception:
        return None


def strip_json_whitespace(source: str) -> str:
    """Remove only insignificant JSON whitespace outside strings."""
    out: list[str] = []
    i = 0
    in_string = False
    escaped = False
    while i < len(source):
        ch = source[i]
        if in_string:
            out.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
        else:
            if ch == '"':
                in_string = True
                out.append(ch)
            elif ch not in " \t\r\n":
                out.append(ch)
        i += 1
    return "".join(out)


def beautify_text(source: str) -> str:
    parsed = Parser(source).parse()
    formatted = format_rpg(parsed)
    # A strict token-level guard: only whitespace outside strings may differ.
    if strip_json_whitespace(source) != strip_json_whitespace(formatted):
        raise JsonFormatError("完整性檢查失敗：輸出內容不只是排版空白差異")
    return formatted + "\n"


def read_text(path: Path) -> str:
    data = path.read_bytes()
    # JSON is normally UTF-8; support UTF-8 BOM and UTF-16 BOM as well.
    if data.startswith(b"\xef\xbb\xbf"):
        return data.decode("utf-8-sig")
    if data.startswith(b"\xff\xfe") or data.startswith(b"\xfe\xff"):
        return data.decode("utf-16")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise JsonFormatError(f"無法以 UTF-8 讀取檔案：{exc}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="RPG MV/MZ JSON lossless formatter")
    parser.add_argument("input", help="來源 JSON 檔案")
    parser.add_argument("output", help="輸出美化檔案（請勿與來源路徑相同）")
    args = parser.parse_args(argv)

    src = Path(args.input).resolve()
    dst = Path(args.output).resolve()
    if src == dst:
        print("錯誤：來源與輸出路徑相同，為避免覆寫原始檔案已取消。", file=sys.stderr)
        return 2

    try:
        original = read_text(src)
        formatted = beautify_text(original)
        dst.parent.mkdir(parents=True, exist_ok=True)
        # UTF-8 output without BOM for predictable WinMerge display.
        dst.write_text(formatted, encoding="utf-8", newline="")
        return 0
    except (OSError, JsonFormatError) as exc:
        print(f"RPGJsonBeautifier: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
