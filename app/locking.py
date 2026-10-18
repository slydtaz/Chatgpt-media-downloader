"""Cross-process locks shared by all installed releases of this application.

Lock files contain no secrets and are kept under the per-user application-data
folder so old/new launchers which share user data coordinate on the same lock.
"""
from __future__ import annotations

import json
import os
import tempfile
import time
import uuid
from pathlib import Path
from typing import Optional

from .config import APP_DATA


class LockBusyError(RuntimeError):
    """Raised when another process owns a cross-process lock."""


class CrossProcessFileLock:
    def __init__(self, path: Path, *, timeout: float = 0.0, poll_interval: float = 0.1):
        self.path = Path(path)
        self.timeout = max(0.0, timeout)
        self.poll_interval = max(0.02, poll_interval)
        self._handle = None
        self._locked = False

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+b")
        try:
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
            deadline = time.monotonic() + self.timeout
            while True:
                handle.seek(0)
                try:
                    if os.name == "nt":
                        import msvcrt
                        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    self._handle = handle
                    self._locked = True
                    return True
                except (OSError, BlockingIOError):
                    if time.monotonic() >= deadline:
                        handle.close()
                        return False
                    time.sleep(self.poll_interval)
        except BaseException:
            handle.close()
            raise

    def release(self) -> None:
        handle = self._handle
        if handle is None:
            return
        try:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except (OSError, ImportError):
            pass
        finally:
            try:
                handle.close()
            finally:
                self._handle = None
                self._locked = False

    def __enter__(self):
        if not self.acquire():
            raise LockBusyError(f"Outro processo está usando o bloqueio {self.path.name}.")
        return self

    def __exit__(self, exc_type, exc, tb):
        self.release()


def _pid_alive(pid: object) -> bool:
    try:
        value = int(pid)
        if value <= 0:
            return False
        if os.name == "nt":
            # os.kill(pid, 0) has inconsistent behavior across Windows Python
            # versions. Query the process handle instead, especially for the
            # short installer handoff window where a false negative can delete
            # the one-time token before the new instance consumes it.
            import ctypes
            from ctypes import wintypes

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
            kernel32.OpenProcess.restype = wintypes.HANDLE
            kernel32.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
            kernel32.GetExitCodeProcess.restype = wintypes.BOOL
            kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
            kernel32.CloseHandle.restype = wintypes.BOOL

            handle = kernel32.OpenProcess(0x1000, False, value)  # PROCESS_QUERY_LIMITED_INFORMATION
            if not handle:
                # Access denied means the process exists but is not queryable.
                return ctypes.get_last_error() == 5
            try:
                exit_code = wintypes.DWORD()
                if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                    return False
                return exit_code.value == 259  # STILL_ACTIVE
            finally:
                kernel32.CloseHandle(handle)

        os.kill(value, 0)
        return True
    except PermissionError:
        return True
    except (OSError, TypeError, ValueError):
        return False


class InstanceGuard:
    """Prevents simultaneous app/bootstrap runs, including installer handoff."""
    def __init__(self, app_data: Path = APP_DATA):
        self.app_data = Path(app_data)
        self.lock_path = self.app_data / "instance.lock"
        self.handoff_path = self.app_data / "instance-handoff.json"
        self._lock: Optional[CrossProcessFileLock] = None
        self.reason = ""

    def _read_handoff(self) -> dict | None:
        try:
            data = json.loads(self.handoff_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else None
        except (OSError, json.JSONDecodeError):
            return None

    def _write_handoff(self, data: dict) -> None:
        self.app_data.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=".instance-handoff-", dir=self.app_data)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(data, handle, ensure_ascii=False)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(name, self.handoff_path)
        finally:
            try:
                os.unlink(name)
            except FileNotFoundError:
                pass

    def create_handoff(self, install_root: Path) -> str:
        token = uuid.uuid4().hex
        self._write_handoff({
            "token": token,
            "owner_pid": os.getpid(),
            "child_pid": None,
            "install_root": str(install_root),
            "created_at": time.time(),
        })
        return token

    def set_handoff_child(self, token: str, child_pid: int) -> None:
        data = self._read_handoff()
        if data and data.get("token") == token:
            data["child_pid"] = int(child_pid)
            self._write_handoff(data)

    def clear_handoff(self, token: str) -> None:
        data = self._read_handoff()
        if data and data.get("token") == token:
            try:
                self.handoff_path.unlink()
            except OSError:
                pass

    def _handoff_active(self) -> bool:
        data = self._read_handoff()
        if not data:
            try:
                self.handoff_path.unlink()
            except OSError:
                pass
            return False
        owner_alive = _pid_alive(data.get("owner_pid"))
        child_alive = _pid_alive(data.get("child_pid"))
        if owner_alive or child_alive:
            return True
        # A crashed installer/child must not block launches indefinitely.
        try:
            self.handoff_path.unlink()
        except OSError:
            pass
        return False

    def acquire(self, *, handoff_token: str | None = None, timeout: float = 0.0) -> bool:
        self.app_data.mkdir(parents=True, exist_ok=True)
        if handoff_token:
            handoff = self._read_handoff()
            if not handoff or handoff.get("token") != handoff_token:
                self.reason = "A passagem para a instalação atualizada expirou. Execute o launcher novamente."
                return False
            timeout = max(timeout, 60.0)
        else:
            if self._handoff_active():
                self.reason = "A atualização ainda está sendo finalizada. Aguarde alguns segundos e tente abrir novamente."
                return False

        lock = CrossProcessFileLock(self.lock_path, timeout=timeout)
        if not lock.acquire():
            self.reason = "O ChatGPT Media Downloader já está aberto ou preparando uma atualização/dependência. Aguarde a operação terminar antes de abrir outra cópia."
            return False

        if handoff_token:
            current = self._read_handoff()
            if not current or current.get("token") != handoff_token:
                lock.release()
                self.reason = "A atualização foi substituída por outra inicialização. Execute o launcher novamente."
                return False
            try:
                self.clear_handoff(handoff_token)
            except Exception:
                lock.release()
                raise
        self._lock = lock
        self.reason = ""
        return True

    def release(self) -> None:
        if self._lock:
            self._lock.release()
            self._lock = None


def show_startup_notice(message: str, title: str = "ChatGPT Media Downloader") -> None:
    """Display a notice without leaving a console window on Windows."""
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, message, title, 0x40 | 0x00040000)
            return
        except Exception:
            pass
    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        messagebox.showinfo(title, message, parent=root)
        root.destroy()
    except Exception:
        # For non-GUI service environments, avoid raising during startup.
        pass
