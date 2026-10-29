# Applying this maintenance update

The archive contains complete replacement files for:

- `README.md`
- `tests/test_formatter.py`

It also adds `THIRD-PARTY-NOTICES.md` and provides a small optional comment-only patch for `src/WinMergeScript.cpp`.

Copy the files while preserving their directory structure. Do not replace `src/RPGJsonBeautifier.py`, the COM interface files, or the working CI workflow as part of this maintenance update.

After copying, run:

```powershell
python -m unittest discover -s tests -v
```

Then run the GitHub Actions workflow and repeat the WinMerge comparison smoke test. These changes improve documentation, attribution, and regression coverage; they do not intentionally change formatting rules.

## Authorship statement

The project-specific formatter and WinMerge bridge were generated and iteratively revised by ChatGPT based on the repository owner's requirements. `src/typeinfoex.h` is based on the cited upstream MIT-licensed implementation; it should not be represented as entirely original ChatGPT-written code. The repository owner defined the requirements and performed the integration/runtime check.
