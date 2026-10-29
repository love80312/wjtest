#ifndef _NEWOBJECTS_ATL_TYPEINFOEX_H_
#define _NEWOBJECTS_ATL_TYPEINFOEX_H_
#include <atlbase.h>
#include <atlcom.h>

// Loads ITypeInfo from the DLL's embedded type library instead of requiring
// registration in the Windows registry. Adapted from the public
// CharlesMengCA/DisplayJSONFiles WinMerge plugin source.
template <int nObtainMethod = 1>
class CComTypeInfoHolderModule : public CComTypeInfoHolder
{
public:
    HRESULT GetTI(LCID lcid, ITypeInfo** ppInfo)
    {
        if (!ppInfo) return E_POINTER;
        HRESULT hr = S_OK;
        if (m_pInfo == NULL) hr = GetTI(lcid);
        *ppInfo = m_pInfo;
        if (m_pInfo) { m_pInfo->AddRef(); hr = S_OK; }
        return hr;
    }
    HRESULT GetTI(LCID lcid)
    {
        if (m_pInfo != NULL) return S_OK;
        EnterCriticalSection(&_Module.m_csTypeInfoHolder);
        if (m_pInfo != NULL) { LeaveCriticalSection(&_Module.m_csTypeInfoHolder); return S_OK; }
        ITypeLib* pTypeLib = NULL;
        TCHAR modulePath[MAX_PATH + 10] = {};
        HRESULT hr = E_FAIL;
        GetModuleFileName(_Module.m_hInstTypeLib, modulePath, MAX_PATH);
        hr = LoadTypeLib(modulePath, &pTypeLib);
        if (SUCCEEDED(hr))
        {
            hr = pTypeLib->GetTypeInfoOfGuid(*m_pguid, &m_pInfo);
            pTypeLib->Release();
        }
        LeaveCriticalSection(&_Module.m_csTypeInfoHolder);
        return hr;
    }
};
#endif
