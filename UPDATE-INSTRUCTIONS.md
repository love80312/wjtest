# Applying this maintenance update

This archive provides complete replacement files and one new file. Preserve the directory structure when copying into the repository:

- Replace `README.md`.
- Replace `tests/test_formatter.py`.
- Replace `src/WinMergeScript.cpp` (the only source change is clarifying a misleading comment; executable behavior is unchanged).
- Add `THIRD-PARTY-NOTICES.md` at the repository root.

No patch application is required. The comment-only change does not require rebuilding the DLL for runtime behavior, but rebuilding the project will include the corrected source comment in the repository going forward.

After copying the files, run:

```powershell
python -m unittest discover -s tests -v
```

Then run the GitHub Actions workflow and repeat the WinMerge comparison smoke test. The expanded tests do not intentionally change formatter rules.

## Authorship statement

The project-specific formatter and WinMerge bridge were generated and iteratively revised by ChatGPT based on the repository owner's requirements. The repository owner defined requirements and performed local installation/runtime verification. `src/typeinfoex.h` is based on the upstream MIT-licensed implementation from CharlesMengCA/DisplayJSONFiles and should not be represented as entirely original code. See `THIRD-PARTY-NOTICES.md`.
