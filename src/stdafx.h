#pragma once
#define STRICT
#ifndef _WIN32_WINNT
#define _WIN32_WINNT 0x0601
#endif
#define _ATL_APARTMENT_THREADED
#include <atlbase.h>
extern CComModule _Module;
#include <atlcom.h>
