# RPGJsonBeautifier

## by AI

A WinMerge unpacker plugin that formats RPG Maker MV/MZ JSON for comparison. The formatter changes whitespace only; it does not intentionally rewrite JSON values or modify the original files.

## Current verification status

The repository owner has verified the following in their WinMerge environment:

- WinMerge recognizes and loads `RPGJsonBeautifier.dll`.
- The plugin formats JSON for comparison.
- Two JSON files containing the same data but different whitespace compare with no differences.

This is a successful basic runtime test, not an exhaustive compatibility test for every JSON file or WinMerge version.

## Requirements

- 64-bit WinMerge.
- Python 3.10 or later available through the Windows Python Launcher (`py -3`). The native DLL starts the formatter with `py -3`; Python is not bundled in the DLL.

## Installation

Close WinMerge and place the following files directly in WinMerge's `MergePlugins` directory:

```text
MergePlugins/
├── RPGJsonBeautifier.dll
├── RPGJsonBeautifier.py
├── RPGJsonBeautifier.ini  # Layout settings (optional; defaults are used when it is missing)
└── DisplayJSONFiles.tlb   # Optional; the type library is also embedded in the DLL
```

When updating, keep your existing `RPGJsonBeautifier.ini` if you have changed it.

Restart WinMerge. Enable **Plugins → Automatic Unpacking** to let WinMerge select the plugin for `.json` files automatically. For troubleshooting, select the plugin manually in the unpacker settings before opening the comparison.

Check that the Python Launcher can start Python from PowerShell:

```powershell
py -3 --version
```

## Formatting rules

The default layout is the same as the standalone *RPG JSON 美化工具* (`RPGgameJSON_9.html`), so text formatted by either tool is identical:

```json
{"name":"Map001",
	"data":[0,0,0,0,0],
	"events":[null,
		{"id":1,
			"name":"EV001",
			"list":[
				{"code":101,"indent":0,"parameters":["","",0,2]},
				{"code":401,"indent":0,"parameters":["哈囉"]}
			]}]}
```

- Arrays containing only numbers and `null` stay on one line, with no spaces: `[0,0,0,0,0]`.
- Arrays of short ASCII letters, digits, and underscore strings (1–9 characters) stay on one line.
- Objects whose values are all empty (`null`, `""`, `[]`, or `{}`) stay on one line. `0` and `false` are real values, not empty ones.
- Short objects whose direct values are all scalars (`{"type":1,"weaponImageId":1}`, `{"name":"","pan":0,"pitch":100,"volume":90}`) stay on one line while they fit in 100 columns (CJK characters count as two columns).
- RPG Maker-style command objects stay on one line when a decoded `code` key exists and every property value is a scalar or an array of scalars.
- Consecutive empty-valued entries (`"a":"","b":null,"c":[]`) share one line (up to 100 columns); adjacent empty strings in an array (`"","",`) share a line too.
- A closing bracket that directly follows another one is merged (`}]}`), `{` joins its first entry, `[` joins a leading `null`, a single wrapper around a numeric array (`[[1,0,0,150]]`) stays on one line, and short boolean arrays (`[true,false]`) stay on one line.
- Preserves object property order, duplicate keys, raw number spellings, and JSON string tokens.
- Verifies the result before it is used: it must be the input with only whitespace between tokens changed (same characters in the same order once whitespace is removed, valid JSON, and every string identical including the whitespace inside it).

### Settings

Every layout switch is in `RPGJsonBeautifier.ini` (next to the script); a missing file or key uses the default shown below.

| Key | Default | Effect |
| --- | --- | --- |
| `tight` | `true` | No space after `,` and `:` → `"data":[0,0,0]`. `false` → `"data": [0, 0, 0]` |
| `hug` | `true` | Merge consecutive closing brackets: `}]}` |
| `tab` | `true` | Indent with Tab; `false` → two spaces |
| `snug` | `true` | `{` joins its first entry; `[` joins a leading `null`; `[[1,2]]` and short `[true,false]` stay on one line |
| `merge_empty` | `true` | Consecutive empty-valued entries, and adjacent `""` in arrays, share a line |
| `wrap` | `false` | Wrap very long numeric arrays at about 100 columns |

The same switches exist as command-line flags for manual runs, for example `py -3 RPGJsonBeautifier.py in.json out.json --no-tight --no-tab`.

These rules reflect the current implementation. Changes to them should be accompanied by regression tests because they affect WinMerge's comparison results. `tests/golden/` holds expected outputs that were produced by the HTML tool.

## Failure behavior and limitations

- The plugin is compare-oriented. Its `PackFile` implementation does not provide a write-back/restore operation; do not treat the transformed comparison view as an editor for saving changes to the original JSON.
- The formatter runs on temporary comparison files. It does not intentionally write the formatted output to the source JSON.
- If Python cannot start, the script is missing, the JSON is invalid, or formatting takes longer than 30 seconds, the native bridge falls back to copying the original content for comparison (a timed-out formatter is killed together with its child process). A comparison window opening successfully does not by itself prove that formatting occurred.
- When the formatter itself rejects a file, the reason (with line and column) is appended to `%TEMP%\RPGJsonBeautifier.log`. Set the environment variable `RPGJSONBEAUTIFIER_LOG` to another path, or to an empty value to disable logging.
- JSON nested deeper than 200 levels is rejected (RPG Maker data is far shallower).
- The formatter currently reads UTF-8 (with or without BOM) and UTF-16 files with a BOM. Its output file is UTF-8 without BOM.
- Python 3.10+ is required because the script uses `X | Y` type unions at run time. Tests run on 3.10 and 3.13 in CI.

## Performance

WinMerge starts the script once per compared file, so both the fixed start-up cost and the per-megabyte cost matter. Measured on a Linux development machine (whole process, including interpreter start; your Windows machine will be slower, the ratios are what counts):

| Input | Before | After |
| --- | --- | --- |
| 8 KB (Actors-like) | 63 ms | 30 ms |
| 0.5 MB (map with events) | 209 ms | 83 ms |
| 4.7 MB (event-heavy) | 1.8 s | 1.1 s |

What makes the difference:
- Only `json`, `os`, `re`, `sys` and `collections` are imported at start-up (a test guards this); `argparse`, `dataclasses`, `pathlib`, `tempfile` and `configparser` cost about 25 ms together.
- Numeric arrays and "flat" objects (event commands, actors, items) are parsed with one regular-expression match each instead of one match per token. A test checks that the result is identical to the token-by-token parser, including which documents are rejected.
- The integrity check removes whitespace with `str.replace` and uses the C JSON scanner instead of four regular-expression passes.

## Tests and build

Run the formatter tests:

```powershell
python -m unittest discover -s tests -v
```

The GitHub Actions workflow runs these tests on Python 3.10 and 3.13, then builds the x64 COM DLL with MSBuild, and packages the DLL, Python script, and generated type library. CI build success does not replace a WinMerge runtime test.

## Authorship and code provenance

The project-specific formatter and WinMerge bridge were generated and iteratively revised by ChatGPT based on the repository owner's requirements. The repository owner supplied the requirements and carried out the local installation and runtime verification. This statement describes the development process; it is not a substitute for third-party license notices.

**Third-party component:** `src/typeinfoex.h` is based on the `typeinfoex.h` implementation from [CharlesMengCA/DisplayJSONFiles](https://github.com/CharlesMengCA/DisplayJSONFiles), which is distributed under the MIT License. That upstream file also attributes the underlying `CComTypeInfoHolder` adaptation to Michael Elfial / newObjects (2001). See [`THIRD-PARTY-NOTICES.md`](THIRD-PARTY-NOTICES.md) and retain the relevant notices when redistributing the project.
