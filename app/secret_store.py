"""Secrets bound to the current Windows account; excluded from business exports."""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
from .validation import DomainError

class Blob(ctypes.Structure):
    _fields_=[('size',wintypes.DWORD),('data',ctypes.POINTER(ctypes.c_ubyte))]

def protect(content, decrypt=False):
    if os.name!='nt': raise DomainError('Ta konfiguracja Google Drive wymaga ochrony danych w Windows.')
    crypt=ctypes.WinDLL('crypt32',use_last_error=True); kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.LocalFree.argtypes=[ctypes.c_void_p]; kernel.LocalFree.restype=ctypes.c_void_p
    buffer=ctypes.create_string_buffer(content); source=Blob(len(content),ctypes.cast(buffer,ctypes.POINTER(ctypes.c_ubyte))); output=Blob()
    if decrypt:
        function=crypt.CryptUnprotectData
        function.argtypes=[ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(Blob)]
        success=function(ctypes.byref(source),None,None,None,None,1,ctypes.byref(output))
    else:
        function=crypt.CryptProtectData
        function.argtypes=[ctypes.POINTER(Blob),wintypes.LPCWSTR,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(Blob)]
        success=function(ctypes.byref(source),'Centrum Kariery — Google Drive',None,None,None,1,ctypes.byref(output))
    if not success: raise DomainError('Windows nie może zabezpieczyć lub odczytać autoryzacji. Dodaj konfigurację ponownie na tym koncie Windows.')
    try: return ctypes.string_at(output.data,output.size)
    finally: kernel.LocalFree(ctypes.cast(output.data,ctypes.c_void_p))

class SecretStore:
    NAMES={'client','token','folder'}
    def __init__(self,directory): self.directory=Path(directory)/'.secrets'
    def path(self,name):
        if name not in self.NAMES: raise ValueError('Unknown secret')
        return self.directory/(name+'.dpapi')
    def read(self,name):
        path=self.path(name)
        if not path.exists(): return None
        if path.is_symlink() or path.stat().st_size>100000: raise DomainError('Nieprawidłowy plik autoryzacji.')
        try: return json.loads(protect(path.read_bytes(),True))
        except (ValueError,UnicodeError): raise DomainError('Nie można odczytać autoryzacji. Dodaj konfigurację ponownie.')
    def write(self,name,value):
        content=protect(json.dumps(value,ensure_ascii=False).encode('utf-8'))
        if self.directory.is_symlink(): raise DomainError('Nieprawidłowy katalog autoryzacji.')
        self.directory.mkdir(exist_ok=True)
        path=self.path(name); temporary=path.with_suffix('.tmp')
        if path.is_symlink() or temporary.is_symlink(): raise DomainError('Nieprawidłowy plik autoryzacji.')
        temporary.write_bytes(content); temporary.replace(path)
    def remove(self,name): self.path(name).unlink(missing_ok=True)
