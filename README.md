# RPGJsonBeautifier

A WinMerge JSON comparison helper intended for RPG Maker MV/MZ JSON files.

## Status

This repository is an initial source setup. The Python formatter core has 5 regression tests, but the native WinMerge COM/Unpacker DLL has **not yet been compiled or verified in WinMerge**. Do not treat this as an install-ready plugin.

## Intended behavior

- Format JSON in a temporary comparison view, without modifying original game files.
- Preserve raw numeric spellings, object key order, and duplicate keys.
- Integrate with WinMerge through its Unpacker/FILE_PACK_UNPACK plugin interface.
- Build and test using GitHub Actions on Windows x64.

## Local Python tests

```powershell
python -m unittest discover -s tests -v
```

## Build status

The workflow runs formatter tests and attempts to build the x64 C++ project using MSBuild. A failed native build means the draft COM bridge still needs correction. A successful DLL compilation alone does not prove that WinMerge can load or correctly use the plugin; runtime integration testing is still required.
