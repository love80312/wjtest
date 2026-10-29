# RPGJsonBeautifier

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
└── DisplayJSONFiles.tlb   # Optional; the type library is also embedded in the DLL
```

Restart WinMerge. Enable **Plugins → Automatic Unpacking** to let WinMerge select the plugin for `.json` files automatically. For troubleshooting, select the plugin manually in the unpacker settings before opening the comparison.

Check that the Python Launcher can start Python from PowerShell:

```powershell
py -3 --version
```

## Formatting rules

- Uses two-space indentation for multiline objects and arrays.
- Keeps arrays containing only numbers and `null` on one line.
- Keeps arrays of short ASCII letters, digits, and underscore strings (1–9 characters) on one line.
- Keeps objects whose values are all considered empty (`null`, `false`, numeric zero, `""`, empty arrays, or empty objects) on one line.
- Keeps RPG Maker-style command objects on one line when a decoded `code` key exists and every property value is a scalar or an array of scalars.
- Preserves object property order, duplicate keys, raw number spellings, and JSON string tokens.
- Runs a token-level check to ensure only whitespace outside strings changes.

These rules reflect the current implementation. Changes to them should be accompanied by regression tests because they affect WinMerge's comparison results.

## Failure behavior and limitations

- The plugin is compare-oriented. Its `PackFile` implementation does not provide a write-back/restore operation; do not treat the transformed comparison view as an editor for saving changes to the original JSON.
- The formatter runs on temporary comparison files. It does not intentionally write the formatted output to the source JSON.
- If Python cannot start, the script is missing, or the JSON is invalid, the native bridge falls back to copying the original content for comparison. A comparison window opening successfully does not by itself prove that formatting occurred.
- The formatter currently reads UTF-8 (with or without BOM) and UTF-16 files with a BOM. Its output file is UTF-8 without BOM.
- Python 3.10+ is required because the script uses modern type annotations and `Path.write_text(..., newline=...)`.

## Tests and build

Run the formatter tests:

```powershell
python -m unittest discover -s tests -v
```

The GitHub Actions workflow runs these tests, builds the x64 COM DLL with MSBuild, and packages the DLL, Python script, and generated type library. CI build success does not replace a WinMerge runtime test.

## Authorship and code provenance

The project-specific formatter and WinMerge bridge were generated and iteratively revised by ChatGPT based on the repository owner's requirements. The repository owner supplied the requirements and carried out the local installation and runtime verification. This statement describes the development process; it is not a substitute for third-party license notices.

**Third-party component:** `src/typeinfoex.h` is based on the `typeinfoex.h` implementation from [CharlesMengCA/DisplayJSONFiles](https://github.com/CharlesMengCA/DisplayJSONFiles), which is distributed under the MIT License. That upstream file also attributes the underlying `CComTypeInfoHolder` adaptation to Michael Elfial / newObjects (2001). See [`THIRD-PARTY-NOTICES.md`](THIRD-PARTY-NOTICES.md) and retain the relevant notices when redistributing the project.
