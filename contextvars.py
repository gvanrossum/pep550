# Stub for PEP 550.  Names subject to bikeshedding.

import threading
from typing import *

# Type variables.

T = TypeVar('T')  # A type
KT = TypeVar('KT')  # A key type
VT = TypeVar('VT')  # A value type

# Fake thread state so the code works.

class ThreadState(threading.local):  # type: ignore  # See https://github.com/python/typing/issues/1591
    """Dummy corresponding to PyThreadState.

    This implementation is actually thread-local!
    """
    ec: Optional['ExecutionContext'] = None

_ts = ThreadState()

def get_TS() -> ThreadState:
    """Return current ThreadState"""
    return _ts

# Get and set current thread's ExecutionContext.

def get_EC() -> 'ExecutionContext':
    """Return current thread's EC (creating it if necessary)"""
    ts = get_TS()
    if ts.ec is None:
        ts.ec = ExecutionContext(LocalContext(), None)
    return ts.ec

def set_EC(ec: 'ExecutionContext') -> None:
    """Set current thread's EC"""
    ts = get_TS()
    ts.ec = ec

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

    # Methods that take the current context into account

    def get_stack(self) -> List[Optional[T]]:
        ec: Optional['ExecutionContext'] = get_EC()
        values: List[Optional[T]] = []
        while ec is not None:
            if self in ec.lc:
                value: T = ec.lc[self]
                values.append(value)
            else:
                values.append(None)
            ec = ec.back
        return values

    def get(self) -> T:
        """Return topmost value or default"""
        ec: Optional['ExecutionContext'] = get_EC()
        while ec is not None:
            if self in ec.lc:
                value: T = ec.lc[self]
                return value
            ec = ec.back
        if self._default is not _no_default:
            return self._default
        raise LookupError

    def set(self, value: T) -> 'CM[T]':
        """Overwrite topmost value, allows restore()"""
        ec = get_EC()
        lc = ec.lc
        found = self in lc
        if found:
            old_value = lc[self]  # type: Optional[T]
        else:
            old_value = None
        new_lc = lc.add(self, value)
        new_ec = ExecutionContext(new_lc, ec.back)
        set_EC(new_ec)
        return CM(self, old_value, found)

class CM(Generic[T]):
    """Context manager for restoring a ContextVar's previous state.

    var = ContextVar('var')

    def fun():
        old_value = var.get()
        with var.set(<value>):
            # Here var.get() is <value>
            <stuff>
        # Here var.get() is old_value

    Note that the side effect of set() happens immediately;
    __enter__() is a dummy returning self, __exit__() calls restore(),
    and if the object is GC'ed before restore() is called nothing
    happens.  Calling restore() a second time is a no-op.
    """

    def __init__(self, var: ContextVar[T], old_value: Optional[T], found: bool) -> None:
        self._var = var
        self._old_value = old_value
        self._found = found
        self._used = False

    def restore(self) -> None:
        if self._used:
            return
        ec = get_EC()
        lc = ec.lc
        if self._found:
            new_lc = lc.add(self._var, self._old_value)
        else:
            new_lc = lc.delete(self._var)
        new_ec = ExecutionContext(new_lc, ec.back)
        set_EC(new_ec)
        self._used = True

    def __enter__(self) -> 'CM[T]':
        return self

    def __exit__(self, *args: object) -> None:
        self.restore()

class LocalContext(Mapping[KT, VT]):

    def __init__(self, d: Mapping[KT, VT] = {}) -> None:
        self.__d = dict(d)

    def __getitem__(self, key: KT) -> VT:
        return self.__d[key]

    def __len__(self) -> int:
        return len(self.__d)

    def __iter__(self) -> Iterator[KT]:
        return iter(self.__d)

    def __contains__(self, key: object) -> bool:
        return key in self.__d

    # API to create new LocalContext instances.

    def add(self, key: KT, value: VT) -> 'LocalContext[KT, VT]':
        d = dict(self.__d)
        d[key] = value
        return LocalContext(d)

    def delete(self, key: KT) -> 'LocalContext[KT, VT]':
        d = dict(self.__d)
        del d[key]
        return LocalContext(d)

    def merge(self, other: 'LocalContext[KT, VT]') -> 'LocalContext[KT, VT]':
        # Note that for keys in both, self[key] prevails.
        d = dict(other.__d)
        d.update(self)
        return LocalContext(d)

class ContextHolder:
    """Mutable local context object.

    This wraps a LocalContext.
    """

    _bare: LocalContext[ContextVar[object], object]

    def __init__(self) -> None:
        self._bare = LocalContext()

class ExecutionContext:
    """Execution context -- a linked list of LocalContexts.

    To push a local context, use ExecutionContext(lc, ec).
    To pop a local context, use ec.back.
    """

    def __init__(self, lc: LocalContext[Any, Any], back: Optional['ExecutionContext']) -> None:
        self._lc = lc
        self._back = back
        self._depth = 1 if back is None else 1 + back.depth

    @property
    def depth(self) -> int:
        """Number of links in the chain (>= 1)"""
        return self._depth

    @property
    def lc(self) -> LocalContext[Any, Any]:
        return self._lc

    @property
    def back(self) -> Optional['ExecutionContext']:
        return self._back

    def vars(self) -> List[ContextVar[object]]:
        res = list(self._lc)
        seen = set(res)
        back = self._back
        while back is not None:
            for var in back._lc:
                if var not in seen:
                    res.append(var)
                    seen.add(var)
            back = back._back
        return res

    def squash(self) -> 'ExecutionContext':
        """Return an equivalent EC with depth 1"""
        lc = self._lc
        back = self._back
        while back is not None:
            lc = lc.merge(back.lc)
            back = back._back
        return ExecutionContext(LocalContext(lc), None)

# Show how the original run_with_*_context() can be implemented:

def run_with_context(ec: ExecutionContext, ch: Optional[ContextHolder], fn: Callable[..., T], *args: object, **kwds: object) -> T:
    """Run fn with this LC pushed on top of ec, then extract values back"""
    if ch is None:
        ch = ContextHolder()
    old_ec = get_EC()
    new_ec = ExecutionContext(ch._bare, ec)
    try:
        set_EC(new_ec)
        return fn(*args, **kwds)
    finally:
        ch._bare = get_EC().lc
        set_EC(old_ec)

def run_with_EC(ec: ExecutionContext, fn: Callable[..., T], *args: object, **kwds: object) -> T:
    """Sets given EC with an empty LC, call fn(), and restore previous EC"""
    return run_with_context(ec, None, fn, *args, **kwds)

def run_with_LC(lc: ContextHolder, fn: Callable[..., T], *args: object, **kwds: object) -> T:
    """Push given LC on top of current EC, call fn(), and restore previous EC"""
    old_ec = get_EC()
    return run_with_context(old_ec, lc, fn, *args, **kwds)
