"""Parse legacy runner strings using the host platform's argument rules."""

from __future__ import annotations

import os
import shlex


def split_runner_command(command: str) -> list[str]:
    """Return argv without executing a shell; prefer argv-list profiles.

    POSIX shell quoting removes Windows path backslashes. On Windows use the
    native argument parser instead, including quoted paths and escaped quotes.
    """
    if not command.strip():
        return []
    if os.name != "nt":
        return shlex.split(command)

    import ctypes
    from ctypes import wintypes

    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    parse = shell32.CommandLineToArgvW
    parse.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_int)]
    parse.restype = ctypes.POINTER(wintypes.LPWSTR)
    free = kernel32.LocalFree
    free.argtypes = [wintypes.HLOCAL]
    free.restype = wintypes.HLOCAL
    count = ctypes.c_int()
    argv = parse(command.lstrip(), ctypes.byref(count))
    if not argv:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return [argv[index] for index in range(count.value)]
    finally:
        free(ctypes.cast(argv, wintypes.HLOCAL))
