import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import unittest
from RPGJsonBeautifier import beautify_text, JsonFormatError, strip_json_whitespace


class FormatterTests(unittest.TestCase):
    def test_compact_and_multiline_same_tokens(self):
        a = '{"name":"Test","list":[1,2,null],"empty":{},"flag":false}'
        out = beautify_text(a)
        self.assertIn('"list": [1, 2, null]', out)
        self.assertIn('"empty": {}', out)
        self.assertEqual(strip_json_whitespace(a), strip_json_whitespace(out))

    def test_duplicate_keys_are_preserved(self):
        src = '{"x":1,"x":2}'
        out = beautify_text(src)
        self.assertEqual(out.count('"x"'), 2)
        self.assertEqual(strip_json_whitespace(src), strip_json_whitespace(out))

    def test_number_literals_are_preserved(self):
        src = '{"id":9007199254740993,"exp":1e+03,"zero":-0}'
        out = beautify_text(src)
        self.assertIn('9007199254740993', out)
        self.assertIn('1e+03', out)
        self.assertIn('-0', out)
        self.assertEqual(strip_json_whitespace(src), strip_json_whitespace(out))

    def test_invalid_json_rejected(self):
        for src in ('{"x":1,}', '[1,]', '{"x":}', '01', '"bad\nstring"'):
            with self.subTest(src=src):
                with self.assertRaises(JsonFormatError):
                    beautify_text(src)

    def test_rpg_command_inline(self):
        src = '{"list":[{"code":101,"indent":0,"parameters":["Hello",1]}]}'
        out = beautify_text(src)
        self.assertIn('{"code": 101, "indent": 0, "parameters": ["Hello", 1]}', out)


if __name__ == "__main__":
    unittest.main()
