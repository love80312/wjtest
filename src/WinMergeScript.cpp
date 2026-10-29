// WinMergeScript.cpp : RPGJsonBeautifier WinMerge Unpacker bridge
#include "stdafx.h"
#include "DisplayJSONFiles.h"
#include "WinMergeScript.h"
#include <windows.h>
#include <string>
#include <vector>
#include <cwchar>

using std::wstring;

STDMETHODIMP CWinMergeScript::get_PluginEvent(BSTR* pVal)
{
    if (!pVal) return E_POINTER;
    *pVal = SysAllocString(L"FILE_PACK_UNPACK");
    return *pVal ? S_OK : E_OUTOFMEMORY;
}

STDMETHODIMP CWinMergeScript::get_PluginDescription(BSTR* pVal)
{
    if (!pVal) return E_POINTER;
    *pVal = SysAllocString(L"RPG MV/MZ JSON beautifier (Python, compare-only)");
    return *pVal ? S_OK : E_OUTOFMEMORY;
}

STDMETHODIMP CWinMergeScript::get_PluginFileFilters(BSTR* pVal)
{
    if (!pVal) return E_POINTER;
    *pVal = SysAllocString(L"\\.json$");
    return *pVal ? S_OK : E_OUTOFMEMORY;
}

STDMETHODIMP CWinMergeScript::get_PluginIsAutomatic(VARIANT_BOOL* pVal)
{
    if (!pVal) return E_POINTER;
    *pVal = VARIANT_TRUE;
    return S_OK;
}

STDMETHODIMP CWinMergeScript::UnpackBufferA(SAFEARRAY** /*pBuffer*/, INT* /*pSize*/,
    VARIANT_BOOL* /*pbChanged*/, INT* /*pSubcode*/, VARIANT_BOOL* pbSuccess)
{
    // FILE_PACK_UNPACK uses the file API; buffer API is intentionally unused.
    if (pbSuccess) *pbSuccess = VARIANT_FALSE;
    return S_OK;
}

STDMETHODIMP CWinMergeScript::PackBufferA(SAFEARRAY** /*pBuffer*/, INT* /*pSize*/,
    VARIANT_BOOL* /*pbChanged*/, INT /*subcode*/, VARIANT_BOOL* pbSuccess)
{
    if (pbSuccess) *pbSuccess = VARIANT_FALSE;
    return S_OK;
}

static wstring QuoteArg(const wstring& arg)
{
    // Quote an argument according to the Windows command-line parsing rules.
    wstring out = L"\"";
    size_t slashes = 0;
    for (wchar_t ch : arg)
    {
        if (ch == L'\\')
        {
            ++slashes;
        }
        else if (ch == L'"')
        {
            out.append(slashes * 2 + 1, L'\\');
            out.push_back(L'"');
            slashes = 0;
        }
        else
        {
            out.append(slashes, L'\\');
            slashes = 0;
            out.push_back(ch);
        }
    }
    out.append(slashes * 2, L'\\');
    out.push_back(L'"');
    return out;
}

static bool GetWinMergeDirectory(wstring& directory)
{
    std::vector<wchar_t> buffer(32768, L'\0');
    const DWORD length = GetModuleFileNameW(nullptr, buffer.data(),
        static_cast<DWORD>(buffer.size()));
    if (length == 0 || length >= buffer.size())
        return false;

    const wstring exePath(buffer.data(), length);
    const size_t slash = exePath.find_last_of(L"\\/");
    if (slash == wstring::npos)
        return false;

    directory = exePath.substr(0, slash + 1);
    return true;
}

static bool CopySourceToDestination(const wchar_t* source, const wchar_t* destination)
{
    // WinMerge supplies a temporary destination path. Do not overwrite if it exists.
    return CopyFileW(source, destination, FALSE) != FALSE;
}

static bool RunFormatter(const wstring& source, const wstring& destination)
{
    wstring winMergeDir;
    if (!GetWinMergeDirectory(winMergeDir))
        return false;

    const wstring script = winMergeDir + L"MergePlugins\\RPGJsonBeautifier.py";
    const DWORD attributes = GetFileAttributesW(script.c_str());
    if (attributes == INVALID_FILE_ATTRIBUTES ||
        (attributes & FILE_ATTRIBUTE_DIRECTORY) != 0)
        return false;

    // Requires the Python Launcher (`py.exe`) to be available on PATH.
    // The formatter uses only the Python standard library.
    wstring command = QuoteArg(L"py") + L" -3 " + QuoteArg(script) +
        L" " + QuoteArg(source) + L" " + QuoteArg(destination);

    STARTUPINFOW startup = {};
    startup.cb = sizeof(startup);
    PROCESS_INFORMATION process = {};
    std::vector<wchar_t> mutableCommand(command.begin(), command.end());
    mutableCommand.push_back(L'\0');

    const BOOL created = CreateProcessW(
        nullptr,
        mutableCommand.data(),
        nullptr,
        nullptr,
        FALSE,
        CREATE_NO_WINDOW,
        nullptr,
        winMergeDir.c_str(),
        &startup,
        &process);

    if (!created)
        return false;

    const DWORD waitResult = WaitForSingleObject(process.hProcess, INFINITE);
    DWORD exitCode = 1;
    const BOOL gotExitCode = GetExitCodeProcess(process.hProcess, &exitCode);
    CloseHandle(process.hThread);
    CloseHandle(process.hProcess);

    return waitResult == WAIT_OBJECT_0 && gotExitCode && exitCode == 0;
}

STDMETHODIMP CWinMergeScript::UnpackFile(BSTR fileSrc, BSTR fileDst,
    VARIANT_BOOL* pbChanged, INT* pSubcode, VARIANT_BOOL* pbSuccess)
{
    if (!fileSrc || !fileDst || !pbChanged || !pSubcode || !pbSuccess)
        return E_POINTER;

    *pbChanged = VARIANT_FALSE;
    *pSubcode = 0;
    *pbSuccess = VARIANT_FALSE;

    if (_wcsicmp(fileSrc, fileDst) == 0)
        return S_OK;

    if (RunFormatter(fileSrc, fileDst))
    {
        *pbChanged = VARIANT_TRUE;
        *pbSuccess = VARIANT_TRUE;
        return S_OK;
    }

    // Invalid JSON, missing Python, or formatter errors: compare original bytes.
    // If the fallback copy fails, report failure rather than fake a successful unpack.
    if (CopySourceToDestination(fileSrc, fileDst))
    {
        *pbChanged = VARIANT_FALSE;
        *pbSuccess = VARIANT_TRUE;
    }
    return S_OK;
}

STDMETHODIMP CWinMergeScript::PackFile(BSTR /*fileSrc*/, BSTR /*fileDst*/,
    VARIANT_BOOL* pbChanged, INT /*pSubcode*/, VARIANT_BOOL* pbSuccess)
{
    // Compare-only plugin: never write the transformed view back to a JSON file.
    if (pbChanged) *pbChanged = VARIANT_FALSE;
    if (pbSuccess) *pbSuccess = VARIANT_FALSE;
    return S_OK;
}

STDMETHODIMP CWinMergeScript::ShowSettingsDialog(VARIANT_BOOL* pbHandled)
{
    if (!pbHandled) return E_POINTER;
    *pbHandled = VARIANT_FALSE;
    return E_NOTIMPL;
}
