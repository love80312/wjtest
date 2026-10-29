import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from RPGJsonBeautifier import (  # noqa: E402
    JsonFormatError,
    beautify_text,
    main,
    read_text,
    strip_json_whitespace,
)


class FormatterTests(unittest.TestCase):
    def assert_preserves_json_tokens(self, source: str, formatted: str) -> None:
        self.assertEqual(
            strip_json_whitespace(source),
            strip_json_whitespace(formatted),
        )
        # Also verify that the formatted text remains syntactically valid JSON.
        json.loads(formatted)

    def test_compact_and_multiline_same_tokens(self):
        source = '{"name":"Test","list":[1,2,null],"empty":{},"flag":false}'
        output = beautify_text(source)

        self.assertIn('"list": [1, 2, null]', output)
        self.assertIn('"empty": {}', output)
        self.assert_preserves_json_tokens(source, output)

    def test_duplicate_keys_are_preserved(self):
        source = '{"x":1,"x":2}'
        output = beautify_text(source)

        self.assertEqual(output.count('"x"'), 2)
        self.assert_preserves_json_tokens(source, output)

    def test_number_literals_are_preserved(self):
        source = '{"id":9007199254740993,"exp":1e+03,"zero":-0}'
        output = beautify_text(source)

        self.assertIn('9007199254740993', output)
        self.assertIn('1e+03', output)
        self.assertIn('-0', output)
        self.assert_preserves_json_tokens(source, output)

    def test_invalid_json_is_rejected(self):
        invalid_documents = (
            '{"x":1,}',
            '[1,]',
            '{"x":}',
            '01',
            '"bad\nstring"',
            r'{"x":"\q"}',
            r'{"x":"\u12XZ"}',
            '{"x":1} trailing',
        )

        for source in invalid_documents:
            with self.subTest(source=source):
                with self.assertRaises(JsonFormatError):
                    beautify_text(source)

    def test_rpg_command_object_is_inline(self):
        source = '{"list":[{"code":101,"indent":0,"parameters":["Hello",1]}]}'
        output = beautify_text(source)

        self.assertIn(
            '{"code": 101, "indent": 0, "parameters": ["Hello", 1]}',
            output,
        )
        self.assert_preserves_json_tokens(source, output)

    def test_escaped_strings_and_unicode_tokens_are_preserved(self):
        source = r'{"quote":"say \"hi\"","path":"C:\\Games\\RPG","escaped":"\\n","unicode":"\u4F60\u597D"}'
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
        output = beautify_text(source)

        self.assertIn('"codes": ["A", "abc123", "_x9"]', output)
        self.assertIn('"labels": [\n', output)
        self.assert_preserves_json_tokens(source, output)

    def test_all_empty_values_object_is_inline(self):
        source = '{"a":null,"b":false,"c":0,"d":"","e":[],"f":{}}'
        output = beautify_text(source)

        self.assertIn(
            '{"a": null, "b": false, "c": 0, "d": "", "e": [], "f": {}}',
            output,
        )
        self.assert_preserves_json_tokens(source, output)

    def test_nested_arrays_and_consecutive_nulls_remain_valid(self):
        source = '{"list":[{"x":1},[true,false],null,null,{"y":[2,3]}]}'
        output = beautify_text(source)

        self.assert_preserves_json_tokens(source, output)
        self.assertEqual(json.loads(source), json.loads(output))

    def test_object_property_order_is_preserved(self):
        source = '{"z":1,"a":2,"m":3}'
        output = beautify_text(source)

        self.assertLess(output.index('"z"'), output.index('"a"'))
        self.assertLess(output.index('"a"'), output.index('"m"'))
        self.assert_preserves_json_tokens(source, output)

    def test_formatting_is_idempotent(self):
        source = '{"name":"Test","list":[1,2,null],"events":[{"code":101,"parameters":["Hi"]}]}'
        once = beautify_text(source)
        twice = beautify_text(once)

        self.assertEqual(once, twice)

    def test_root_scalar_and_root_array_are_supported(self):
        for source in ('true', 'null', '123', '[1,2,3]', '["A","B"]'):
            with self.subTest(source=source):
                output = beautify_text(source)
                self.assert_preserves_json_tokens(source, output)

    def test_read_text_supports_bom_encodings(self):
        text = '{"message":"繁體中文"}'
        payloads = (
            text.encode("utf-8-sig"),
            text.encode("utf-16"),
            b'\xff\xfe' + text.encode("utf-16-le"),
            b'\xfe\xff' + text.encode("utf-16-be"),
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "encoding.json"
            for payload in payloads:
                with self.subTest(prefix=payload[:4]):
                    path.write_bytes(payload)
                    self.assertEqual(read_text(path), text)

    def test_cli_writes_utf8_without_bom(self):
        source_text = '{"message":"繁體中文"}'

        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source.json"
            output = Path(temp_dir) / "formatted.json"
            source.write_text(source_text, encoding="utf-8")

            result = main([str(source), str(output)])

            self.assertEqual(result, 0)
            output_bytes = output.read_bytes()
            self.assertFalse(output_bytes.startswith(b"\xef\xbb\xbf"))
            self.assertEqual(json.loads(output_bytes.decode("utf-8")), json.loads(source_text))
            self.assertEqual(source.read_text(encoding="utf-8"), source_text)

    def test_cli_refuses_same_input_and_output_path(self):
        source_text = '{"message":"keep original"}'

        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "same.json"
            source.write_text(source_text, encoding="utf-8")
            stderr = io.StringIO()

            with contextlib.redirect_stderr(stderr):
                result = main([str(source), str(source)])

            self.assertEqual(result, 2)
            self.assertEqual(source.read_text(encoding="utf-8"), source_text)
            self.assertIn("路徑相同", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
