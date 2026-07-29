"""基础设施模块——合并 utils / bounded_dict / workset 的共享工具集。

包含：
- safe_ensure_future: 安全的异步任务调度
- BoundedDict: 带 LRU 驱逐和可选 TTL 过期的有界字典
- build_fragment_workset: 工作集构建（黑板/碎片模式）
- resolve_data_root: 数据目录解析（含旧路径自动迁移）
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import stat
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any, Callable, Protocol, cast

try:
    from astrbot.api import logger  # type: ignore
    from astrbot.core.utils.astrbot_path import get_astrbot_data_path  # type: ignore
except ImportError:
    logger = logging.getLogger("astrbot_plugin_sylanne")  # type: ignore

    def get_astrbot_data_path() -> Path:  # type: ignore
        return Path.home()


_PLUGIN_NAME = "astrbot_plugin_sylanne"
_LEGACY_SUBDIR = "sylanne_alpha"


class _WindowsHandle(Protocol):
    def __int__(self) -> int: ...

    def Close(self) -> None: ...


class _WindowsAcl(Protocol):
    def GetAceCount(self) -> int: ...

    def GetAce(self, index: int, /) -> tuple[tuple[int, int], int, Any]: ...


class _WindowsSecurityDescriptor(Protocol):
    def GetSecurityDescriptorOwner(self) -> Any: ...

    def GetSecurityDescriptorDacl(self) -> _WindowsAcl | None: ...

    def GetSecurityDescriptorControl(self) -> tuple[int, int]: ...


def resolve_data_root(config: dict[str, Any] | None = None) -> str:
    """解析 Sylanne 数据存储根目录，遵循 AstrBot plugin_data 规范。

    优先级：
      1. config["sylanne_alpha_root"]（用户显式指定）
      2. data/plugin_data/astrbot_plugin_sylanne/（规范路径）
      3. 若规范路径不存在但旧路径 data/sylanne_alpha/ 存在，自动迁移

    Returns:
        数据根目录的字符串路径。
    """
    cfg = config or {}
    explicit = cfg.get("sylanne_alpha_root")
    if explicit:
        return str(explicit)

    base = Path(get_astrbot_data_path())
    new_root = base / "plugin_data" / _PLUGIN_NAME
    legacy_root = base / _LEGACY_SUBDIR

    if new_root.exists():
        return str(new_root)

    if legacy_root.exists():
        try:
            new_root.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(legacy_root), str(new_root))
            logger.info(f"Sylanne: migrated data {legacy_root} → {new_root}")
        except Exception as e:
            logger.warning(f"Sylanne: data migration failed ({e}), using legacy path")
            return str(legacy_root)

    new_root.mkdir(parents=True, exist_ok=True)
    return str(new_root)


def resolve_scope_v1_root() -> Path:
    """Return the isolated scope-v1 root without consulting legacy data helpers."""

    from astrbot.api.star import StarTools  # type: ignore

    root = Path(StarTools.get_data_dir(_PLUGIN_NAME)) / "scope-v1"
    root.mkdir(parents=True, exist_ok=True)
    return root


# ---------------------------------------------------------------------------
# Owner-only persistent secret files
# ---------------------------------------------------------------------------


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    offset = 0
    while offset < len(view):
        written = os.write(fd, view[offset:])
        if written <= 0:
            raise OSError("secret write made no progress")
        offset += written


def _validate_secret_payload(
    data: bytes,
    *,
    magic: bytes,
    secret_bytes: int,
    error_label: str,
) -> bytes:
    if not data.startswith(magic):
        raise ValueError(f"{error_label} has an invalid header")
    secret = data[len(magic) :]
    if len(secret) != secret_bytes:
        raise ValueError(f"{error_label} has an invalid length")
    return secret


def _sync_parent_if_supported(path: Path) -> None:
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _current_effective_uid() -> int:
    get_effective_uid = getattr(os, "geteuid", None)
    if not callable(get_effective_uid):
        raise OSError("effective user identity is unavailable on this platform")
    uid = get_effective_uid()
    if type(uid) is not int:
        raise OSError("effective user identity has an invalid type")
    return uid


def _validate_posix_owner_only(
    path: Path,
    *,
    directory: bool,
    error_label: str,
) -> os.stat_result:
    try:
        info = path.lstat()
    except OSError as exc:
        raise ValueError(f"{error_label} permissions could not be inspected") from exc
    expected = stat.S_ISDIR if directory else stat.S_ISREG
    if not expected(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise ValueError(f"{error_label} path has an invalid file type")
    if info.st_uid != _current_effective_uid():
        raise ValueError(f"{error_label} owner does not match the current user")
    if stat.S_IMODE(info.st_mode) & 0o077:
        raise ValueError(f"{error_label} permissions are not owner-only")
    if not directory and info.st_nlink != 1:
        raise ValueError(f"{error_label} must have exactly one hard link")
    return info


def _load_posix_secret(
    path: Path,
    *,
    magic: bytes,
    secret_bytes: int,
    error_label: str,
) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise ValueError(f"{error_label} could not be opened securely") from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != _current_effective_uid():
            raise ValueError(f"{error_label} owner or file type is invalid")
        if stat.S_IMODE(info.st_mode) & 0o077 or info.st_nlink != 1:
            raise ValueError(f"{error_label} permissions are not owner-only")
        maximum = len(magic) + secret_bytes + 1
        chunks: list[bytes] = []
        remaining = maximum
        while remaining > 0:
            chunk = os.read(fd, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        return _validate_secret_payload(
            b"".join(chunks),
            magic=magic,
            secret_bytes=secret_bytes,
            error_label=error_label,
        )
    finally:
        os.close(fd)


def _windows_security_attributes():
    import ntsecuritycon
    import pywintypes
    import win32api
    import win32con
    import win32security

    token = cast(
        _WindowsHandle,
        win32security.OpenProcessToken(
            win32api.GetCurrentProcess(),
            win32con.TOKEN_QUERY,
        ),
    )
    try:
        owner_sid = win32security.GetTokenInformation(
            int(token),
            win32security.TokenUser,
        )[0]
    finally:
        token.Close()
    admin_sid = win32security.CreateWellKnownSid(
        win32security.WinBuiltinAdministratorsSid,
        None,
    )
    system_sid = win32security.CreateWellKnownSid(
        win32security.WinLocalSystemSid,
        None,
    )
    dacl = pywintypes.ACL()
    for sid in (owner_sid, admin_sid, system_sid):
        dacl.AddAccessAllowedAceEx(
            win32security.ACL_REVISION,
            0,
            ntsecuritycon.FILE_ALL_ACCESS,
            sid,
        )
    descriptor = pywintypes.SECURITY_DESCRIPTOR()
    descriptor.SetSecurityDescriptorOwner(owner_sid, False)
    descriptor.SetSecurityDescriptorDacl(True, dacl, False)
    descriptor.SetSecurityDescriptorControl(
        win32security.SE_DACL_PROTECTED,
        win32security.SE_DACL_PROTECTED,
    )
    attributes = pywintypes.SECURITY_ATTRIBUTES()
    attributes.bInheritHandle = False
    attributes.SECURITY_DESCRIPTOR = descriptor
    return attributes, owner_sid, dacl


def _validate_windows_descriptor(
    descriptor: _WindowsSecurityDescriptor,
    *,
    error_label: str,
) -> None:
    import ntsecuritycon
    import win32security

    _attributes, owner_sid, _dacl = _windows_security_attributes()
    sid_text = win32security.ConvertSidToStringSid
    allowed = {
        sid_text(owner_sid),
        sid_text(
            win32security.CreateWellKnownSid(
                win32security.WinBuiltinAdministratorsSid,
                None,
            )
        ),
        sid_text(
            win32security.CreateWellKnownSid(
                win32security.WinLocalSystemSid,
                None,
            )
        ),
    }
    owner = descriptor.GetSecurityDescriptorOwner()
    dacl = descriptor.GetSecurityDescriptorDacl()
    control, _revision = descriptor.GetSecurityDescriptorControl()
    if sid_text(owner) != sid_text(owner_sid):
        raise ValueError(f"{error_label} owner does not match the current user")
    if dacl is None or not control & win32security.SE_DACL_PROTECTED:
        raise ValueError(f"{error_label} ACL is missing or inherits permissions")
    found: set[str] = set()
    for index in range(dacl.GetAceCount()):
        header, mask, sid = dacl.GetAce(index)
        ace_type, ace_flags = header
        resolved = sid_text(sid)
        if (
            ace_type != ntsecuritycon.ACCESS_ALLOWED_ACE_TYPE
            or ace_flags & win32security.INHERITED_ACE
            or mask != ntsecuritycon.FILE_ALL_ACCESS
            or resolved not in allowed
        ):
            raise ValueError(f"{error_label} ACL contains an unauthorized entry")
        found.add(resolved)
    if found != allowed or dacl.GetAceCount() != len(allowed):
        raise ValueError(f"{error_label} ACL is not the exact owner-only policy")


def _validate_windows_path(path: Path, *, error_label: str) -> None:
    import win32security

    descriptor = win32security.GetNamedSecurityInfo(
        str(path),
        win32security.SE_FILE_OBJECT,
        win32security.OWNER_SECURITY_INFORMATION | win32security.DACL_SECURITY_INFORMATION,
    )
    _validate_windows_descriptor(descriptor, error_label=error_label)


def _secure_windows_parent(
    path: Path,
    *,
    key_exists: bool,
    error_label: str,
) -> None:
    import pywintypes
    import win32file
    import win32security
    import winerror

    path.parent.mkdir(parents=True, exist_ok=True)
    attributes, owner_sid, dacl = _windows_security_attributes()
    try:
        win32file.CreateDirectory(str(path), attributes)
    except pywintypes.error as exc:
        if exc.winerror not in {winerror.ERROR_ALREADY_EXISTS, winerror.ERROR_FILE_EXISTS}:
            raise
        if not key_exists:
            current = win32security.GetNamedSecurityInfo(
                str(path),
                win32security.SE_FILE_OBJECT,
                win32security.OWNER_SECURITY_INFORMATION,
            )
            current_owner = current.GetSecurityDescriptorOwner()
            if win32security.ConvertSidToStringSid(current_owner) != win32security.ConvertSidToStringSid(owner_sid):
                raise ValueError(f"{error_label} directory owner is invalid")
            win32security.SetNamedSecurityInfo(
                str(path),
                win32security.SE_FILE_OBJECT,
                win32security.DACL_SECURITY_INFORMATION | win32security.PROTECTED_DACL_SECURITY_INFORMATION,
                None,
                None,
                dacl,
                None,
            )
    _validate_windows_path(path, error_label=error_label)


def _flush_windows_handle(handle: _WindowsHandle) -> None:
    import win32file

    win32file.FlushFileBuffers(int(handle))


def _load_windows_secret(
    path: Path,
    *,
    magic: bytes,
    secret_bytes: int,
    error_label: str,
) -> bytes:
    import win32con
    import win32file
    import win32security

    attributes = win32file.GetFileAttributes(str(path))
    if attributes & win32con.FILE_ATTRIBUTE_REPARSE_POINT:
        raise ValueError(f"{error_label} path must not be a reparse point")
    handle: _WindowsHandle = win32file.CreateFile(
        str(path),
        win32con.GENERIC_READ | win32con.READ_CONTROL,
        win32con.FILE_SHARE_READ,
        None,
        win32con.OPEN_EXISTING,
        win32con.FILE_ATTRIBUTE_NORMAL | win32file.FILE_FLAG_OPEN_REPARSE_POINT,
        None,
    )
    try:
        descriptor = win32security.GetSecurityInfo(
            int(handle),
            win32security.SE_FILE_OBJECT,
            win32security.OWNER_SECURITY_INFORMATION | win32security.DACL_SECURITY_INFORMATION,
        )
        _validate_windows_descriptor(descriptor, error_label=error_label)
        result, data = cast(
            tuple[int, object],
            win32file.ReadFile(int(handle), len(magic) + secret_bytes + 1),
        )
        if result != 0:
            raise OSError(f"{error_label} read failed with status {result}")
        if type(data) is not bytes:
            raise OSError(f"{error_label} read returned a non-bytes payload")
        return _validate_secret_payload(
            data,
            magic=magic,
            secret_bytes=secret_bytes,
            error_label=error_label,
        )
    finally:
        handle.Close()


def _create_windows_secret(
    path: Path,
    payload: bytes,
    *,
    magic: bytes,
    secret_bytes: int,
    error_label: str,
    flush_windows_handle: Callable[[_WindowsHandle], None],
) -> bytes:
    import pywintypes
    import win32con
    import win32file
    import win32security
    import winerror

    temp_path = path.with_name(f".{path.name}.{os.urandom(12).hex()}.tmp")
    attributes, _owner_sid, _dacl = _windows_security_attributes()
    try:
        handle: _WindowsHandle = win32file.CreateFile(
            str(temp_path),
            win32con.GENERIC_WRITE | win32con.READ_CONTROL,
            0,
            attributes,
            win32con.CREATE_NEW,
            win32con.FILE_ATTRIBUTE_NORMAL,
            None,
        )
        try:
            descriptor = win32security.GetSecurityInfo(
                int(handle),
                win32security.SE_FILE_OBJECT,
                win32security.OWNER_SECURITY_INFORMATION | win32security.DACL_SECURITY_INFORMATION,
            )
            _validate_windows_descriptor(descriptor, error_label=error_label)
            result, written = win32file.WriteFile(int(handle), payload)
            if result != 0 or written != len(payload):
                raise OSError(f"{error_label} write was incomplete")
            flush_windows_handle(handle)
        finally:
            handle.Close()
        try:
            win32file.MoveFileEx(
                str(temp_path),
                str(path),
                win32file.MOVEFILE_WRITE_THROUGH,
            )
        except pywintypes.error as exc:
            if exc.winerror not in {winerror.ERROR_ALREADY_EXISTS, winerror.ERROR_FILE_EXISTS}:
                raise
    finally:
        try:
            win32file.DeleteFile(str(temp_path))
        except pywintypes.error as exc:
            if exc.winerror != winerror.ERROR_FILE_NOT_FOUND:
                raise
    return _load_windows_secret(
        path,
        magic=magic,
        secret_bytes=secret_bytes,
        error_label=error_label,
    )


def _load_persistent_secret(
    path: Path,
    *,
    magic: bytes,
    secret_bytes: int,
    error_label: str,
) -> bytes:
    if os.name == "nt":
        return _load_windows_secret(
            path,
            magic=magic,
            secret_bytes=secret_bytes,
            error_label=error_label,
        )
    return _load_posix_secret(
        path,
        magic=magic,
        secret_bytes=secret_bytes,
        error_label=error_label,
    )


def _create_posix_secret(
    path: Path,
    payload: bytes,
    *,
    magic: bytes,
    secret_bytes: int,
    error_label: str,
) -> bytes:
    temp_path = path.with_name(f".{path.name}.{os.urandom(12).hex()}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    fd = os.open(temp_path, flags, 0o600)
    try:
        _write_all(fd, payload)
        os.fsync(fd)
    finally:
        os.close(fd)
    try:
        os.link(temp_path, path, follow_symlinks=False)
    except FileExistsError:
        pass
    finally:
        temp_path.unlink(missing_ok=True)
    _sync_parent_if_supported(path.parent)
    return _load_posix_secret(
        path,
        magic=magic,
        secret_bytes=secret_bytes,
        error_label=error_label,
    )


def load_or_create_owner_only_secret(
    path: str | os.PathLike[str],
    *,
    magic: bytes,
    secret_bytes: int,
    error_label: str,
    flush_windows_handle: Callable[[_WindowsHandle], None] | None = None,
) -> bytes:
    """Load or exclusively create an owner-only persistent secret.

    Existing malformed or weakly protected files always fail closed.  The optional
    flush callback is intentionally injectable so legacy callers retain their
    platform-specific fault-injection seam.
    """

    if type(magic) is not bytes or not magic:
        raise TypeError("magic must be non-empty exact bytes")
    if type(secret_bytes) is not int or secret_bytes < 1:
        raise ValueError("secret_bytes must be a positive int")
    if type(error_label) is not str or not error_label:
        raise ValueError("error_label must be a non-empty str")
    key_path = Path(path)
    key_exists = key_path.exists()
    if os.name == "nt":
        _secure_windows_parent(
            key_path.parent,
            key_exists=key_exists,
            error_label=error_label,
        )
    else:
        key_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if not key_exists:
            os.chmod(key_path.parent, 0o700)
        _validate_posix_owner_only(
            key_path.parent,
            directory=True,
            error_label=error_label,
        )
    if key_exists:
        return _load_persistent_secret(
            key_path,
            magic=magic,
            secret_bytes=secret_bytes,
            error_label=error_label,
        )

    secret = os.urandom(secret_bytes)
    payload = magic + secret
    if os.name == "nt":
        return _create_windows_secret(
            key_path,
            payload,
            magic=magic,
            secret_bytes=secret_bytes,
            error_label=error_label,
            flush_windows_handle=flush_windows_handle or _flush_windows_handle,
        )
    return _create_posix_secret(
        key_path,
        payload,
        magic=magic,
        secret_bytes=secret_bytes,
        error_label=error_label,
    )


def atomic_write_owner_only_bytes(
    path: str | os.PathLike[str],
    payload: bytes,
    *,
    error_label: str,
    flush_windows_handle: Callable[[_WindowsHandle], None] | None = None,
) -> None:
    """Atomically replace one file while preserving the owner-only policy."""

    if type(payload) is not bytes:
        raise TypeError("payload must have exact type bytes")
    if type(error_label) is not str or not error_label:
        raise ValueError("error_label must be a non-empty str")
    destination = Path(path)
    exists = destination.exists()
    if os.name == "nt":
        _secure_windows_parent(
            destination.parent,
            key_exists=exists,
            error_label=error_label,
        )
        _atomic_write_windows_owner_only(
            destination,
            payload,
            error_label=error_label,
            flush_windows_handle=flush_windows_handle or _flush_windows_handle,
        )
        return

    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not exists:
        os.chmod(destination.parent, 0o700)
    _validate_posix_owner_only(
        destination.parent,
        directory=True,
        error_label=error_label,
    )
    temporary = destination.with_name(
        f".{destination.name}.{os.urandom(12).hex()}.tmp"
    )
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    fd = os.open(temporary, flags, 0o600)
    try:
        _write_all(fd, payload)
        os.fsync(fd)
    finally:
        os.close(fd)
    try:
        os.replace(temporary, destination)
        _sync_parent_if_supported(destination.parent)
        _validate_posix_owner_only(
            destination,
            directory=False,
            error_label=error_label,
        )
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_write_windows_owner_only(
    path: Path,
    payload: bytes,
    *,
    error_label: str,
    flush_windows_handle: Callable[[_WindowsHandle], None],
) -> None:
    import pywintypes
    import win32con
    import win32file
    import win32security
    import winerror

    temporary = path.with_name(f".{path.name}.{os.urandom(12).hex()}.tmp")
    attributes, _owner_sid, _dacl = _windows_security_attributes()
    try:
        handle: _WindowsHandle = win32file.CreateFile(
            str(temporary),
            win32con.GENERIC_WRITE | win32con.READ_CONTROL,
            0,
            attributes,
            win32con.CREATE_NEW,
            win32con.FILE_ATTRIBUTE_NORMAL,
            None,
        )
        try:
            descriptor = win32security.GetSecurityInfo(
                int(handle),
                win32security.SE_FILE_OBJECT,
                win32security.OWNER_SECURITY_INFORMATION
                | win32security.DACL_SECURITY_INFORMATION,
            )
            _validate_windows_descriptor(descriptor, error_label=error_label)
            result, written = win32file.WriteFile(int(handle), payload)
            if result != 0 or written != len(payload):
                raise OSError(f"{error_label} write was incomplete")
            flush_windows_handle(handle)
        finally:
            handle.Close()
        win32file.MoveFileEx(
            str(temporary),
            str(path),
            win32file.MOVEFILE_REPLACE_EXISTING
            | win32file.MOVEFILE_WRITE_THROUGH,
        )
        _validate_windows_path(path, error_label=error_label)
    finally:
        try:
            win32file.DeleteFile(str(temporary))
        except pywintypes.error as exc:
            if exc.winerror != winerror.ERROR_FILE_NOT_FOUND:
                raise


# ---------------------------------------------------------------------------
# utils: 异步辅助工具
# ---------------------------------------------------------------------------


def ensure_background_tasks_list(p: Any) -> list:
    """Ensure ``p._background_tasks`` is a ``list``, rebuilding when needed.

    If the attribute is missing or is not a :class:`list` (e.g. a ``set``),
    it is rebuilt as ``[]``.  When a type mismatch is detected, a warning
    is logged so the root cause can be traced in production.

    Returns the task list for convenience, allowing callers to write::

        ensure_background_tasks_list(p).append(task)

    instead of duplicating the guard.
    """
    if hasattr(p, "_background_tasks") and isinstance(p._background_tasks, list):
        return p._background_tasks

    if hasattr(p, "_background_tasks"):
        logging.getLogger("astrbot_plugin_sylanne").warning(
            "Sylanne: _background_tasks type mismatch (expected list, got %s), rebuilding",
            type(p._background_tasks).__name__,
        )
    p._background_tasks = []
    return p._background_tasks


def safe_ensure_future(
    coro: Any, name: str = "task", task_list: list | None = None
) -> "asyncio.Task[Any] | None":
    """将协程安全地调度为 asyncio Task，并附加异常日志回调。

    Args:
        coro: 待调度的协程对象。
        name: 任务名称，用于异常日志标识。
        task_list: 可选的任务列表，任务创建时加入、完成时自动移除，
                   便于外部统一管理/取消后台任务。

    Returns:
        创建的 asyncio.Task 实例，或在无运行事件循环时返回 None。
        若返回 None，协程已被关闭以防止资源泄漏。
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No running loop (sync context, init/teardown) — close coro to prevent leak
        coro.close()
        return None
    
    task = loop.create_task(coro)
    if task_list is not None:
        task_list.append(task)

    def _done(t: "asyncio.Task[Any]") -> None:
        # 任务完成后从列表中移除，保持列表只含活跃任务
        if task_list is not None:
            try:
                task_list.remove(t)
            except ValueError:
                pass
        if t.cancelled():
            return
        exc = t.exception()
        if exc:
            logger.warning(f"Sylanne background task [{name}] failed: {exc}")

    task.add_done_callback(_done)
    return task


# ---------------------------------------------------------------------------
# bounded_dict: 带 LRU 驱逐和可选 TTL 过期的有界字典
# ---------------------------------------------------------------------------


class BoundedDict(OrderedDict):
    """带最大容量（LRU 驱逐）和可选 TTL 过期的有序字典。

    继承自 OrderedDict，利用其 move_to_end 实现 O(1) 的 LRU 访问更新。
    驱逐时可触发 on_evict 回调，用于持久化被驱逐的对象（如将 host 状态写盘）。
    """

    def __init__(self, maxsize: int = 200, ttl: float = 0, on_evict=None):
        """初始化有界字典。

        Args:
            maxsize: 最大容量，超出时驱逐最旧条目。
            ttl: 条目存活时间（秒），0 表示不启用 TTL。
            on_evict: 驱逐回调 fn(key, value)，在条目被 LRU 驱逐时调用。
        """
        super().__init__()
        self.maxsize = maxsize
        self.ttl = ttl
        self._ts: dict[Any, float] = {}  # 记录每个 key 的写入时间戳（仅 TTL 模式）
        self._on_evict = on_evict

    def __setitem__(self, key: Any, value: Any) -> None:
        # 已存在的 key 更新时移到末尾，保持 LRU 语义
        if key in self:
            self.move_to_end(key)
        super().__setitem__(key, value)
        if self.ttl:
            self._ts[key] = time.time()
        # 超容量时循环驱逐最旧条目（队首）
        while len(self) > self.maxsize:
            oldest = next(iter(self))
            self._ts.pop(oldest, None)
            value_evicted = super().__getitem__(oldest)
            del self[oldest]
            if self._on_evict:
                try:
                    self._on_evict(oldest, value_evicted)
                except Exception as exc:
                    logger.warning(
                        "BoundedDict on_evict callback failed for key %r: %s",
                        oldest,
                        exc,
                    )

    def __contains__(self, key: Any) -> bool:
        # CP8-P6：TTL 模式下，过期条目视为不存在（与 __getitem__ 的过期语义一致），
        # 修复 get_or_create 等 `key in d`→True 但 `d[key]` 抛 KeyError 的 TOCTOU。
        # 只读判断、不在此删除（避免在 __setitem__ 的 `key in self` 调用里产生副作用）。
        if not super().__contains__(key):
            return False
        if self.ttl and key in self._ts and (time.time() - self._ts[key] > self.ttl):
            return False
        return True

    def __getitem__(self, key: Any) -> Any:
        # TTL 检查：过期则惰性删除并抛出 KeyError
        if self.ttl and key in self._ts:
            if time.time() - self._ts[key] > self.ttl:
                self._ts.pop(key, None)
                del self[key]
                raise KeyError(key)
        # 让底层存储做权威存在性判定：缺失时由 super().__getitem__ 抛出正确的 KeyError。
        # 不能先用 `if key in self` 守 move_to_end——Py3.10 的 C 层 OrderedDict.pop 会路由到
        # 本重写的 __getitem__，与重写的 __contains__ 交互时 move_to_end 可能对“已被 pop 抽走
        # 的 key”抛 KeyError(204)，制造出非真实缺失的伪 KeyError（3.13 的 pop 不路由到此，故只 3.10 炸）。
        value = super().__getitem__(key)  # key 真缺 → 这里抛 KeyError，pop(default) 正常兜底
        try:
            self.move_to_end(key)  # LRU 更新；并发/pop 交互下 key 已不在则忽略
        except KeyError:
            pass
        return value

    def get(self, key: Any, default: Any = None) -> Any:
        """获取值，不存在或已过期时返回 default。"""
        try:
            return self[key]
        except KeyError:
            return default

    def setdefault(self, key: Any, default: Any = None) -> Any:
        """若 key 不存在则设置为 default 并返回。"""
        if key not in self:
            self[key] = default
        return self[key]


# ---------------------------------------------------------------------------
# workset: 工作集构建
# ---------------------------------------------------------------------------

WORKSET_SCHEMA_VERSION = "sylanne.alpha.workset.v1"


def build_fragment_workset(
    *,
    session_key: str,
    fragments: list[str] | None = None,
    shadow: dict[str, Any] | None = None,
    memory_matches: list[dict[str, Any]] | None = None,
    max_items: int = 5,
    dialogue: dict[str, Any] | None = None,
    personality: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
    assessor: dict[str, Any] | None = None,
    guard: dict[str, Any] | None = None,
    attention: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """构建工作集：聚合各子系统证据为统一的 prompt 注入数据结构。

    Args:
        session_key: 会话标识。
        fragments: 当前意图文本碎片列表。
        shadow: 影子连续性数据（上一轮未消费的延续信息）。
        memory_matches: 记忆检索匹配结果列表。
        max_items: 工作集最大条目数。
        dialogue: 对话子系统证据。
        personality: 人格子系统证据。
        body: 身体状态子系统证据。
        assessor: 评估器子系统证据。
        guard: 安全守卫子系统证据。
        attention: 注意力子系统证据。

    Returns:
        工作集字典，包含 items/evidence/coordination/prompt_fragment 等字段。
    """
    # 清洗碎片：去除空白、合并多余空格
    clean_fragments = [
        " ".join(str(fragment).split())
        for fragment in fragments or []
        if str(fragment).strip()
    ]
    current_intent = " ".join(clean_fragments).strip()
    shadow = dict(shadow or {})
    items: list[dict[str, Any]] = []

    # 当前意图权重最高
    if current_intent:
        items.append(
            {"kind": "current_intent", "text": current_intent[:500], "weight": 1.0}
        )
    # 影子连续性：上一轮的延续摘要，权重略低
    if shadow.get("summary"):
        items.append(
            {
                "kind": "shadow_continuity",
                "text": str(shadow["summary"])[:500],
                "weight": 0.85,
            }
        )
    # 记忆匹配：按权重降序排列加入
    for match in sorted(
        memory_matches or [],
        key=lambda item: float(item.get("weight") or 0.0),
        reverse=True,
    ):
        text = str(match.get("text") or "").strip()
        if text:
            items.append(
                {
                    "kind": "memory_match",
                    "id": str(match.get("id") or ""),
                    "text": text[:500],
                    "weight": float(match.get("weight") or 0.0),
                }
            )
    # 去重并截断到 max_items
    items = _dedupe(items)[: max(1, int(max_items))]

    # 影子消费策略：consume_once 表示本轮使用后不再保留
    consume_shadow = bool(shadow.get("consume") and shadow.get("summary"))

    # 收集各部门证据，构建黑板
    evidence = _evidence(
        dialogue=dialogue,
        memory_matches=items,
        personality=personality,
        body=body,
        assessor=assessor,
        guard=guard,
        attention=attention,
    )
    # 协调：决定主导部门和 fast/slow 路径分组
    coordination = _coordination(evidence, attention=attention, guard=guard)

    return {
        "schema_version": WORKSET_SCHEMA_VERSION,
        "session_key": session_key,
        "mode": "blackboard" if evidence else "fragment",
        "current_intent": current_intent,
        "items": items,
        "evidence": evidence,
        "coordination": coordination,
        "shadow": {
            "available": bool(shadow.get("summary")),
            "consumed": consume_shadow,
            "policy": "consume_once" if consume_shadow else "preserve",
        },
        # 根据模式选择渲染方式
        "prompt_fragment": _render_blackboard(evidence, coordination)
        if evidence
        else _render(items),
    }


def _evidence(
    *,
    dialogue: dict[str, Any] | None,
    memory_matches: list[dict[str, Any]],
    personality: dict[str, Any] | None,
    body: dict[str, Any] | None,
    assessor: dict[str, Any] | None,
    guard: dict[str, Any] | None,
    attention: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """收集各部门的证据，标注 fast/slow 路径。

    fast 路径：对话、记忆、身体、守卫、注意力（低延迟，可立即获得）
    slow 路径：人格、评估器（需要 LLM 推理，可能有延迟）
    """
    evidence: list[dict[str, Any]] = []
    for department, payload, path in (
        ("dialogue", dialogue, "fast"),
        (
            "memory",
            {"matches": memory_matches, "count": len(memory_matches)}
            if memory_matches
            else None,
            "fast",
        ),
        ("personality", personality, "slow"),
        ("body", body, "fast"),
        ("assessor", assessor, "slow"),
        ("guard", guard, "fast"),
        ("attention", attention, "fast"),
    ):
        if payload:
            evidence.append(
                {
                    "department": department,
                    "path": path,
                    "summary": _truncate_payload_values(payload),
                }
            )
    return evidence


def _coordination(
    evidence: list[dict[str, Any]],
    *,
    attention: dict[str, Any] | None,
    guard: dict[str, Any] | None,
) -> dict[str, Any]:
    """决定协调策略：主导部门、fast/slow 路径分组。

    优先级：attention 指定 > guard 存在 > 第一个部门 > none。
    核心策略：fast_path_never_waits_for_slow_path（实时性优先）。
    """
    departments = [item["department"] for item in evidence]
    primary = str((attention or {}).get("primary") or "")
    if primary not in departments:
        # guard 存在时优先（安全优先），否则取第一个部门
        primary = (
            "guard"
            if guard and "guard" in departments
            else (departments[0] if departments else "none")
        )
    return {
        "primary_department": primary,
        "fast_path": [
            item["department"] for item in evidence if item["path"] == "fast"
        ],
        "slow_path": [
            item["department"] for item in evidence if item["path"] == "slow"
        ],
        "policy": "fast_path_never_waits_for_slow_path",
    }


def _truncate_payload_values(payload: dict[str, Any]) -> dict[str, Any]:
    """递归截断 payload 中的长文本值，防止工作集过大。

    - 字符串截断到 300 字符
    - 列表截断到前 5 项
    - 跳过敏感/大体积字段（raw/prompt/request/response）
    """
    clean: dict[str, Any] = {}
    for key, value in payload.items():
        if key in {"raw", "raw_text", "raw_dialogue", "prompt", "request", "response"}:
            continue
        if isinstance(value, str):
            clean[key] = value[:300]
        elif isinstance(value, dict):
            clean[key] = _truncate_payload_values(value)
        elif isinstance(value, list):
            clean[key] = [
                _truncate_payload_values(item) if isinstance(item, dict) else item
                for item in value[:5]
            ]
        else:
            clean[key] = value
    return clean


def _render_blackboard(
    evidence: list[dict[str, Any]], coordination: dict[str, Any]
) -> str:
    """将黑板模式的证据渲染为 prompt 文本片段。"""
    if not evidence:
        return "Sylanne blackboard: empty."
    lines = [f"Sylanne blackboard: primary={coordination['primary_department']}"]
    for item in evidence:
        lines.append(f"- {item['department']}[{item['path']}]")
    return "\n".join(lines)


def _dedupe(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按 kind+text 去重，保留首次出现的条目。"""
    seen: set[str] = set()
    deduped = []
    for item in items:
        key = f"{item['kind']}\0{item.get('text', '')}"
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _render(items: list[dict[str, Any]]) -> str:
    """将碎片模式的条目渲染为 prompt 文本片段。"""
    if not items:
        return "Sylanne workset: empty."
    lines = ["Sylanne workset:"]
    for item in items:
        lines.append(f"- {item['kind']}: {item['text']}")
    return "\n".join(lines)


__all__ = [
    "atomic_write_owner_only_bytes",
    "safe_ensure_future",
    "BoundedDict",
    "load_or_create_owner_only_secret",
    "resolve_data_root",
    "resolve_scope_v1_root",
    "WORKSET_SCHEMA_VERSION",
    "build_fragment_workset",
]
