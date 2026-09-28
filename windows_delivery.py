"""Paste a short response frame into the focused Civ VI mod input on Windows."""
from __future__ import annotations

import ctypes
import os
import time


class WindowsDelivery:
    def __init__(self):
        if os.name != "nt":
            raise RuntimeError("遊戲內回答傳遞需要在 Windows 上執行。")
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.user32.GetWindowTextW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
        self.user32.GetWindowTextW.restype = ctypes.c_int
        self.user32.GetForegroundWindow.restype = ctypes.c_void_p
        self.user32.OpenClipboard.argtypes = [ctypes.c_void_p]
        self.user32.OpenClipboard.restype = ctypes.c_int
        self.user32.CloseClipboard.restype = ctypes.c_int
        self.user32.GetClipboardData.argtypes = [ctypes.c_uint]
        self.user32.GetClipboardData.restype = ctypes.c_void_p
        self.user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
        self.user32.SetClipboardData.restype = ctypes.c_void_p
        self.user32.EmptyClipboard.restype = ctypes.c_int
        self.kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
        self.kernel32.GlobalAlloc.restype = ctypes.c_void_p
        self.kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
        self.kernel32.GlobalLock.restype = ctypes.c_void_p
        self.kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
        self.kernel32.GlobalFree.argtypes = [ctypes.c_void_p]
        self._original = None

    def game_is_foreground(self) -> bool:
        title = ctypes.create_unicode_buffer(512)
        self.user32.GetWindowTextW(self.user32.GetForegroundWindow(), title, len(title))
        name = title.value.lower()
        expected = os.environ.get("CIV6_WINDOW_TITLE", "civilization vi").lower()
        return bool(expected and expected in name)

    def _open(self):
        for _ in range(20):
            if self.user32.OpenClipboard(None):
                return
            time.sleep(0.03)
        raise RuntimeError("無法使用 Windows 剪貼簿，請稍後再按「接收回答」。")

    def _get_text(self):
        handle = self.user32.GetClipboardData(13)  # CF_UNICODETEXT
        if not handle:
            return None
        pointer = self.kernel32.GlobalLock(handle)
        if not pointer:
            return None
        try:
            return ctypes.wstring_at(pointer)
        finally:
            self.kernel32.GlobalUnlock(handle)

    def _set_text(self, value: str):
        raw = value.encode("utf-16-le") + b"\0\0"
        handle = self.kernel32.GlobalAlloc(0x0002, len(raw))  # GMEM_MOVEABLE
        if not handle:
            raise RuntimeError("無法配置剪貼簿記憶體。")
        pointer = self.kernel32.GlobalLock(handle)
        ctypes.memmove(pointer, raw, len(raw))
        self.kernel32.GlobalUnlock(handle)
        if not self.user32.EmptyClipboard() or not self.user32.SetClipboardData(13, handle):
            self.kernel32.GlobalFree(handle)
            raise RuntimeError("無法寫入剪貼簿。")

    def paste(self, frame: str) -> bool:
        if not self.game_is_foreground():
            return False
        self._open()
        try:
            if self._original is None:
                self._original = self._get_text()
            self._set_text(frame)
        finally:
            self.user32.CloseClipboard()
        # The mod takes focus on its private receive EditBox when the player clicks Receive.
        self.user32.keybd_event(0x11, 0, 0, 0)  # Ctrl down
        self.user32.keybd_event(0x56, 0, 0, 0)  # V down
        self.user32.keybd_event(0x56, 0, 2, 0)
        self.user32.keybd_event(0x11, 0, 2, 0)
        return True

    def restore_text(self):
        if self._original is not None:
            self._open()
            try:
                self._set_text(self._original)
            finally:
                self.user32.CloseClipboard()
        self._original = None
