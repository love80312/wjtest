import contextlib
import io
import json
import os
import random
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from RPGJsonBeautifier import (  # noqa: E402
    LEGACY,
    JsonFormatError,
    Options,
    beautify_text,
    load_options,
    main,
    parse_json,
    read_text,
    strip_json_whitespace,
    verify_lossless,
)

GOLDEN = Path(__file__).resolve().parent / "golden"


class FormatterTestCase(unittest.TestCase):
    def assert_preserves_json_tokens(self, source: str, formatted: str) -> None:
        self.assertEqual(
            strip_json_whitespace(source),
            strip_json_whitespace(formatted),
        )
        # Also verify that the formatted text remains syntactically valid JSON.
        json.loads(formatted)


class DefaultLayoutTests(FormatterTestCase):
    """Default options reproduce the HTML tool: tight separators, Tab indent, hugged closers."""

    def test_numeric_arrays_have_no_spaces(self):
        source = '{"data":[0, 0, 0, 0, 0],"mixed":[1, null, 3]}'
        output = beautify_text(source)

        self.assertIn('"data":[0,0,0,0,0]', output)
        self.assertIn('"mixed":[1,null,3]', output)
        self.assertNotIn(", ", output)
        self.assert_preserves_json_tokens(source, output)

    def test_tight_off_keeps_spaces(self):
        output = beautify_text('{"data":[0,0,0,0,0]}', Options(tight=False))

        self.assertIn('"data": [0, 0, 0, 0, 0]', output)

    def test_tab_indent_and_two_space_indent(self):
        source = '{"a":{"b":{"c":1}}}'

        self.assertIn('\n\t\t"b":', beautify_text(source))
        self.assertIn('\n    "b":', beautify_text(source, Options(tab=False, snug=False)))

    def test_closing_brackets_are_hugged(self):
        source = '{"list":[{"a":{"b":1,"c":2}}]}'

        self.assertTrue(beautify_text(source).rstrip().endswith("}]}"))
        self.assertTrue(beautify_text(source, Options(hug=False)).rstrip().endswith("}"))
        self.assertNotIn("}]}", beautify_text(source, Options(hug=False)))

    def test_single_numeric_wrapper_stays_on_one_line(self):
        source = '{"tile":[[1,0,0,150]],"deep":[[[1,2]]]}'
        output = beautify_text(source)

        self.assertIn('"tile":[[1,0,0,150]]', output)
        self.assertIn('"deep":[[[1,2]]]', output)
        self.assertNotIn("[[1,0,0,150]]", beautify_text(source, Options(snug=False)))

    def test_snug_opening_brace_and_leading_null(self):
        source = '[null,{"id":1,"name":"A","note":"x"}]'
        output = beautify_text(source)

        self.assertTrue(output.startswith("[null,\n"))
        self.assertIn('\t{"id":1,\n', output)
        plain = beautify_text(source, Options(snug=False))
        self.assertTrue(plain.startswith("[\n"))
        self.assertIn("\t{\n", plain)

    def test_consecutive_empty_entries_share_a_line(self):
        source = '{"id":1,"a":"","b":null,"c":[],"d":{},"name":"x"}'
        output = beautify_text(source)

        self.assertIn('"a":"","b":null,"c":[],"d":{},', output)
        self.assertEqual(beautify_text(source, Options(merge_empty=False)).count('"a"'), 1)
        self.assertNotIn('"a":"","b":null', beautify_text(source, Options(merge_empty=False)))
        self.assert_preserves_json_tokens(source, output)

    def test_long_numeric_array_wraps_only_when_enabled(self):
        source = json.dumps({"data": list(range(1000, 1060))})
        flat = beautify_text(source)
        wrapped = beautify_text(source, Options(wrap=True, snug=False, tab=False))

        self.assertEqual(sum('"data"' in line for line in flat.splitlines()), 1)
        self.assertGreater(len(wrapped.splitlines()), len(flat.splitlines()))
        self.assertTrue(all(len(line) <= 100 for line in wrapped.splitlines()))
        self.assert_preserves_json_tokens(source, wrapped)

    def test_formatting_is_idempotent_for_every_option_combination(self):
        source = '{"name":"Test","list":[1,2,null],"events":[null,{"code":101,"parameters":["Hi"]},{"a":"","b":null}]}'
        for bits in range(64):
            opts = Options(*(bool(bits >> i & 1) for i in range(6)))
            with self.subTest(options=opts):
                once = beautify_text(source, opts)
                self.assertEqual(once, beautify_text(once, opts))


class GoldenTests(FormatterTestCase):
    """Expected files were produced by the HTML tool (RPGgameJSON_8.html) itself."""

    def check(self, name: str, suffix: str, options: Options) -> None:
        source = (GOLDEN / f"{name}.in.json").read_text(encoding="utf-8")
        expected = (GOLDEN / f"{name}.{suffix}.out.json").read_text(encoding="utf-8")

        self.assertEqual(beautify_text(source, options), expected)

    def test_map(self):
        self.check("map", "default", Options())

    def test_actors(self):
        self.check("actors", "default", Options())

    def test_system(self):
        self.check("system", "default", Options())

    def test_map_spaced_and_wrapped(self):
        self.check("map", "spaced_wrapped", Options(wrap=True, hug=True, tight=False, tab=False, snug=False, merge_empty=False))


class ParserTests(FormatterTestCase):
    def test_compact_and_multiline_same_tokens(self):
        source = '{"name":"Test","list":[1,2,null],"empty":{},"flag":false}'
        output = beautify_text(source, LEGACY)

        self.assertIn('"list": [1, 2, null]', output)
        self.assertIn('"empty": {}', output)
        self.assert_preserves_json_tokens(source, output)

    def test_duplicate_keys_are_preserved(self):
        source = '{"x":1,"x":2}'
        output = beautify_text(source)

        self.assertEqual(output.count('"x"'), 2)
        self.assert_preserves_json_tokens(source, output)

    def test_number_literals_are_preserved(self):
        source = '{"id":9007199254740993,"exp":1e+03,"zero":-0,"list":[1E5,0.50,-0.0]}'
        output = beautify_text(source)

        for literal in ("9007199254740993", "1e+03", "-0", "1E5", "0.50", "-0.0"):
            self.assertIn(literal, output)
        self.assert_preserves_json_tokens(source, output)

    def test_invalid_json_is_rejected(self):
        invalid_documents = (
            '', '   ', '[', '{"a"', '{"x":1,}', '[1,]', '{"x":}', '01', '"bad\nstring"',
            r'{"x":"\q"}', r'{"x":"\u12XZ"}', '{"x":1} trailing', '[1 2]', '[1,,2]', '[1.]', '[1e]',
            '[-]', '[01]', '[+1]', '[.5]', '[NaN]', '[Infinity]', "{'a':1}", '{"a" 1}', '{1:2}', '[}', '{]',
            '[1]]', '[true false]', '[nul]', '"unterminated',
        )
        for source in invalid_documents:
            with self.subTest(source=source):
                with self.assertRaises(JsonFormatError):
                    beautify_text(source)

    def test_error_message_has_line_and_column(self):
        with self.assertRaises(JsonFormatError) as caught:
            parse_json('{\n  "a": 1,\n  "b": ?\n}')

        self.assertIn("第 3 行", str(caught.exception))

    def test_parser_agrees_with_json_loads_on_mutated_documents(self):
        rng = random.Random(7)
        base = '{"a":[1,2,[3,{"b":"x\\n\\u00e9"}],null,true],"c":{"d":-1.5e3,"e":[]},"f":"\\"q\\""}'
        alphabet = list('{}[],:"\\ \n01-.eEtrufalsn') + ["\x01", "é"]

        def strict(text):
            def reject(name):
                raise ValueError(name)
            try:
                json.loads(text, parse_constant=reject)
                return True
            except ValueError:
                return False

        for _ in range(3000):
            chars = list(base)
            for _ in range(rng.choice([1, 2, 3])):
                i = rng.randrange(len(chars))
                action = rng.random()
                if action < 0.35:
                    del chars[i]
                elif action < 0.7:
                    chars.insert(i, rng.choice(alphabet))
                else:
                    chars[i] = rng.choice(alphabet)
            text = "".join(chars)
            try:
                parse_json(text)
                accepted = True
            except JsonFormatError:
                accepted = False
            self.assertEqual(accepted, strict(text), text)

    def test_huge_numeric_array_uses_fast_path_correctly(self):
        values = [(i * 37) % 4000 for i in range(120_000)]
        source = '{"data":[' + ",\n ".join(map(str, values)) + "]}"
        output = beautify_text(source)

        self.assertEqual(json.loads(output)["data"], values)
        self.assertEqual(output.count("\n"), 1)                                  # one line + final newline
        self.assertEqual(beautify_text(source, Options(snug=False)).count("\n"), 3)  # {, "data":[...], }

    def test_nesting_limit_gives_clear_error(self):
        beautify_text("[" * 150 + "]" * 150)
        with self.assertRaises(JsonFormatError) as caught:
            beautify_text("[" * 5000 + "]" * 5000)

        self.assertIn("巢狀", str(caught.exception))

    def test_rpg_command_object_is_inline(self):
        source = '{"list":[{"code":101,"indent":0,"parameters":["Hello",1]}]}'

        self.assertIn('{"code": 101, "indent": 0, "parameters": ["Hello", 1]}', beautify_text(source, LEGACY))
        self.assertIn('{"code":101,"indent":0,"parameters":["Hello",1]}', beautify_text(source))
        self.assertIn('{"\\u0063ode":1,"p":[2]}', beautify_text('{"\\u0063ode":1,"p":[2]}'))   # escaped key still counts

    def test_escaped_strings_and_unicode_tokens_are_preserved(self):
        source = r'{"quote":"say \"hi\"","path":"C:\\Games\\RPG","escaped":"\\n","unicode":"\u4F60\u597D","slash":"\/"}'
        output = beautify_text(source)

        self.assert_preserves_json_tokens(source, output)
        self.assertEqual(json.loads(source), json.loads(output))

    def test_literal_non_ascii_text_is_preserved(self):
        source = '{"text":"繁體中文、遊戲資料、😀"}'
        output = beautify_text(source)

        self.assertIn('繁體中文、遊戲資料、😀', output)
        self.assert_preserves_json_tokens(source, output)

    def test_short_ascii_string_array_is_inline(self):
        source = '{"codes":["A","abc123","_x9"],"labels":["long-label-10","繁體"]}'
        output = beautify_text(source, LEGACY)

        self.assertIn('"codes": ["A", "abc123", "_x9"]', output)
        self.assertIn('"labels": [\n', output)
        self.assert_preserves_json_tokens(source, output)

    def test_all_empty_values_object_is_inline(self):
        source = '{"a":null,"b":false,"c":0,"d":"","e":[],"f":{}}'

        self.assertIn('{"a": null, "b": false, "c": 0, "d": "", "e": [], "f": {}}', beautify_text(source, LEGACY))
        self.assertIn('{"a":null,"b":false,"c":0,"d":"","e":[],"f":{}}', beautify_text(source))

    def test_nested_arrays_and_consecutive_nulls_remain_valid(self):
        source = '{"list":[{"x":1},[true,false],null,null,{"y":[2,3]}]}'
        output = beautify_text(source)

        self.assert_preserves_json_tokens(source, output)
        self.assertEqual(json.loads(source), json.loads(output))
        self.assertIn("null,null,", output)

    def test_object_property_order_is_preserved(self):
        output = beautify_text('{"z":1,"a":2,"m":3}')

        self.assertLess(output.index('"z"'), output.index('"a"'))
        self.assertLess(output.index('"a"'), output.index('"m"'))

    def test_root_scalar_and_root_array_are_supported(self):
        for source in ('true', 'null', '123', '[1,2,3]', '["A","B"]', '[]', '{}'):
            with self.subTest(source=source):
                self.assert_preserves_json_tokens(source, beautify_text(source))

    def test_every_option_combination_is_lossless_on_random_documents(self):
        rng = random.Random(2026)

        def make(depth):
            r = rng.random()
            if depth == 0 or r < 0.3:
                return rng.choice([0, 1, -7, 2.5, None, True, "", "abc", "哈囉", "q\"x", 1e3])
            if r < 0.5:
                return [rng.choice([0, 1, 22, None]) for _ in range(rng.choice([0, 1, 3, 40]))]
            if r < 0.6:
                return [[rng.choice([1, 2, 3]) for _ in range(rng.choice([1, 3]))]]
            if r < 0.8:
                return [make(depth - 1) for _ in range(rng.choice([1, 2, 4]))]
            keys = rng.sample(["id", "code", "name", "a", "b", "c", "d", "note"], rng.choice([1, 3, 6]))
            return {k: ("" if rng.random() < 0.4 else make(depth - 1)) for k in keys}

        for _ in range(60):
            source = json.dumps(make(4), ensure_ascii=rng.random() < 0.5)
            for bits in (0, 63, 21, 42, 5, 58):
                opts = Options(*(bool(bits >> i & 1) for i in range(6)))
                output = beautify_text(source, opts)
                self.assertEqual(json.loads(output), json.loads(source))


class IntegrityGateTests(unittest.TestCase):
    def test_accepts_whitespace_only_changes(self):
        verify_lossless('{"a": [1, 2]}', '{\n\t"a":[1,2]\n}')

    def test_rejects_every_kind_of_tampering(self):
        source = '{"a":[10,2],"s":"x y","t":true,"n":1e5}'
        tampered = {
            "changed value": '{"a":[11,2],"s":"x y","t":true,"n":1e5}',
            "number split": '{"a":[1 0,2],"s":"x y","t":true,"n":1e5}',
            "exponent split": '{"a":[10,2],"s":"x y","t":true,"n":1 e5}',
            "string whitespace changed": '{"a":[10,2],"s":"x  y","t":true,"n":1e5}',
            "token dropped": '{"a":[10],"s":"x y","t":true,"n":1e5}',
            "junk inserted": '{"a":[10,2];"s":"x y","t":true,"n":1e5}',
            "literal split": '{"a":[10,2],"s":"x y","t":tr ue,"n":1e5}',
        }
        for label, output in tampered.items():
            with self.subTest(label):
                with self.assertRaises(JsonFormatError):
                    verify_lossless(source, output)


class ConfigAndCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.dir = Path(self.temp.name)
        self.log = self.dir / "beautifier.log"
        patcher = mock.patch.dict(os.environ, {"RPGJSONBEAUTIFIER_LOG": str(self.log)})
        patcher.start()
        self.addCleanup(patcher.stop)

    def write_ini(self, text: str) -> Path:
        path = self.dir / "settings.ini"
        path.write_text(text, encoding="utf-8")
        return path

    def test_missing_config_gives_defaults(self):
        self.assertEqual(load_options(self.dir / "missing.ini"), Options())

    def test_config_values_override_defaults(self):
        path = self.write_ini("[format]\ntight = no   ; keep spaces\ntab = false\nwrap = 1\n")

        self.assertEqual(load_options(path), Options(tight=False, tab=False, wrap=True))

    def test_bad_config_value_falls_back_and_is_logged(self):
        path = self.write_ini("[format]\ntight = maybe\nhug = false\n")

        self.assertEqual(load_options(path), Options(hug=False))
        self.assertIn("tight", self.log.read_text(encoding="utf-8"))

    def test_shipped_ini_matches_default_options(self):
        shipped = Path(__file__).resolve().parents[1] / "src" / "RPGJsonBeautifier.ini"

        self.assertEqual(load_options(shipped), Options())

    def test_read_text_supports_bom_encodings(self):
        text = '{"message":"繁體中文"}'
        payloads = (
            text.encode("utf-8-sig"),
            text.encode("utf-16"),
            b'\xff\xfe' + text.encode("utf-16-le"),
            b'\xfe\xff' + text.encode("utf-16-be"),
        )
        path = self.dir / "encoding.json"
        for payload in payloads:
            with self.subTest(prefix=payload[:4]):
                path.write_bytes(payload)
                self.assertEqual(read_text(path), text)

    def test_cli_writes_utf8_without_bom_and_leaves_source_alone(self):
        source_text = '{"message":"繁體中文","data":[0, 0, 0]}'
        source, output = self.dir / "source.json", self.dir / "formatted.json"
        source.write_text(source_text, encoding="utf-8")

        result = main([str(source), str(output), "--config", str(self.dir / "none.ini")])

        self.assertEqual(result, 0)
        data = output.read_bytes()
        self.assertFalse(data.startswith(b"\xef\xbb\xbf"))
        self.assertNotIn(b"\r", data)
        self.assertIn(b'"data":[0,0,0]', data)
        self.assertEqual(source.read_text(encoding="utf-8"), source_text)

    def test_cli_flags_override_config(self):
        ini = self.write_ini("[format]\ntight = true\n")
        source, output = self.dir / "s.json", self.dir / "o.json"
        source.write_text('{"data":[0,0]}', encoding="utf-8")

        self.assertEqual(main([str(source), str(output), "--config", str(ini), "--no-tight", "--no-tab"]), 0)

        self.assertIn('"data": [0, 0]', output.read_text(encoding="utf-8"))

    def test_cli_refuses_same_input_and_output_path(self):
        source_text = '{"message":"keep original"}'
        source = self.dir / "same.json"
        source.write_text(source_text, encoding="utf-8")
        stderr = io.StringIO()

        with contextlib.redirect_stderr(stderr):
            result = main([str(source), str(source)])

        self.assertEqual(result, 2)
        self.assertEqual(source.read_text(encoding="utf-8"), source_text)
        self.assertIn("路徑相同", stderr.getvalue())

    def test_invalid_json_returns_1_writes_nothing_and_is_logged(self):
        source, output = self.dir / "bad.json", self.dir / "out.json"
        source.write_text('{"a":1,}', encoding="utf-8")

        with contextlib.redirect_stderr(io.StringIO()):
            result = main([str(source), str(output)])

        self.assertEqual(result, 1)
        self.assertFalse(output.exists())
        self.assertIn("bad.json", self.log.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
