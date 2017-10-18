# Simpler context vars.

import threading
from typing import *

# Type variables.

T = TypeVar('T')  # A type
KT = TypeVar('KT')  # A key type
VT = TypeVar('VT')  # A value type

# Fake thread state so the code works.

class ThreadState(threading.local):  # type: ignore  # See https://github.com/python/typeshed/issues/1591
    """Dummy corresponding to PyThreadState.

    This implementation is actually thread-local!
    """
    ctx: Optional['Context'] = None

_ts = ThreadState()

def get_TS() -> ThreadState:
    """Return current ThreadState."""
    return _ts

# Get and set current thread's Context.

def get_ctx() -> 'Context':
    """Return current thread's context (creating it if necessary)."""
    ts = get_TS()
    if ts.ctx is None:
        ts.ctx = Context()
    return ts.ctx

def _set_ctx(ctx: 'Context') -> None:
    """Set current thread's context."""
    ts = get_TS()
    ts.ctx = ctx

_no_default: Any = object()

class ContextVar(Generic[T]):
    """Context variable."""

    def __init__(self, name: str, *, default: T = _no_default) -> None:
        self._name = name
        self._default = default

    @property
    def name(self) -> str:
        return self._name

    @property
    def default(self) -> T:
        return self._default

    # Methods that take the current context into account.

    def get(self, default: T = _no_default) -> T:
        """Return current value."""
        ctx: 'Context' = get_ctx()
        if self in ctx:
            return ctx[self]
        if default is not _no_default:
            return default
        if self._default is not _no_default:
            return self._default
        raise LookupError

    def set(self, value: T) -> None:
        """Overwrite current value."""
        ctx: 'Context' = get_ctx()
        ctx[self] = value

    def delete(self) -> None:
        """Delete current value."""
        ctx: 'Context' = get_ctx()
        if self in ctx:
            del ctx[self]
        elif self._default is not _no_default:
            pass
        else:
            raise LookupError

class AbstractContext(MutableMapping[KT, VT]):

    def __init__(self, d: Mapping[KT, VT] = {}) -> None:
        self.__d = dict(d)  # Maybe a weakkeydict?

    def __getitem__(self, key: KT) -> VT:
        return self.__d[key]

    def __setitem__(self, key: KT, value: VT) -> None:
        self.__d[key] = value

    def __delitem__(self, key: KT) -> None:
        del self.__d[key]

    def __len__(self) -> int:
        return len(self.__d)

    def __iter__(self) -> Iterator[KT]:
        return iter(self.__d)

    def __contains__(self, key: object) -> bool:
        return key in self.__d

    # For other methods, the defaults in MutableMapping suffice.

class Context(AbstractContext[ContextVar, Any]):

    def run(self, func: Callable[..., T], *args, **kwds) -> T:
        saved = get_ctx()
        try:
            _set_ctx(self)
            return func(*args, **kwds)
        finally:
            _set_ctx(saved)
