// WinMergeScript.h
#ifndef __WINMERGESCRIPT_H_
#define __WINMERGESCRIPT_H_
#include "resource.h"
#include "typeinfoex.h"

typedef CComTypeInfoHolderModule<1> CComTypeInfoHolderFileOnly;

class ATL_NO_VTABLE CWinMergeScript :
    public CComObjectRootEx<CComSingleThreadModel>,
    public CComCoClass<CWinMergeScript, &CLSID_WinMergeScript>,
    public IDispatchImpl<IWinMergeScript, &IID_IWinMergeScript,
        &LIBID_DisplayJSONFilesLib, 1, 0, CComTypeInfoHolderFileOnly>
{
public:
    CWinMergeScript() {}

    DECLARE_REGISTRY_RESOURCEID(IDR_WINMERGESCRIPT)
    DECLARE_PROTECT_FINAL_CONSTRUCT()

    BEGIN_COM_MAP(CWinMergeScript)
        COM_INTERFACE_ENTRY(IWinMergeScript)
        COM_INTERFACE_ENTRY(IDispatch)
    END_COM_MAP()

    STDMETHOD(PackFile)(BSTR fileSrc, BSTR fileDst, VARIANT_BOOL* pbChanged,
        INT pSubcode, VARIANT_BOOL* pbSuccess);
    STDMETHOD(UnpackFile)(BSTR fileSrc, BSTR fileDst, VARIANT_BOOL* pbChanged,
        INT* pSubcode, VARIANT_BOOL* pbSuccess);
    STDMETHOD(PackBufferA)(SAFEARRAY** pBuffer, INT* pSize, VARIANT_BOOL* pbChanged,
        INT subcode, VARIANT_BOOL* pbSuccess);
    STDMETHOD(UnpackBufferA)(SAFEARRAY** pBuffer, INT* pSize, VARIANT_BOOL* pbChanged,
        INT* pSubcode, VARIANT_BOOL* pbSuccess);
    STDMETHOD(ShowSettingsDialog)(VARIANT_BOOL* pbHandled);
    STDMETHOD(get_PluginIsAutomatic)(VARIANT_BOOL* pVal);
    STDMETHOD(get_PluginFileFilters)(BSTR* pVal);
    STDMETHOD(get_PluginDescription)(BSTR* pVal);
    STDMETHOD(get_PluginEvent)(BSTR* pVal);
};
#endif
