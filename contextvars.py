# Stub for PEP 550.  Names subject to bikeshedding.

import threading
from typing import *

# Type variables.

T = TypeVar('T')  # A type
S = TypeVar('S')  # Another type
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
        ts.ec = ExecutionContext(FrozenDict(), None, 1)
    return ts.ec

def set_EC(ec: 'ExecutionContext') -> None:
    """Set current thread's EC"""
    ts = get_TS()
    ts.ec = ec

class ContextVar(Generic[T, S]):
    """Context variable."""

    def __init__(self, name: str, *, default: S) -> None:
        self._name = name
        self._default = default

    @property
    def name(self) -> str:
        return self._name

    @property
    def default(self) -> S:
        return self._default

    # Methods that take the current context into account

    def get(self) -> Union[T, S]:
        """Return topmost value or default"""
        ec: Optional['ExecutionContext'] = get_EC()
        while ec is not None:
            if self in ec.lc:
                value: T = ec.lc[self]
                return value
            ec = ec.back
        return self._default

    def set(self, value: T) -> None:
        """Overwrite topmost value"""
        old_ec = get_EC()
        new_lc = old_ec.lc.add(self, value)
        new_ec = ExecutionContext(new_lc, old_ec.back, old_ec.depth)
        set_EC(new_ec)

    def setx(self, value: T) -> 'CM':
        """Overwrite topmost value, allows restore()"""
        ec = get_EC()
        lc = ec.lc
        found = self in lc
        if found:
            old_value = lc[self]
        else:
            old_value = None
        new_lc = lc.add(self, value)
        new_ec = ExecutionContext(new_lc, ec.back, ec.depth)
        set_EC(new_ec)
        return CM(self, old_value, found)

class CM:
    """Context manager for restoring a ContextVar's previous state.

    var = ContextVar('var')

    def fun():
        old_value = var.get()
        with var.setx(<value>):
            # Here var.get() is <value>
            <stuff>
        # Here var.get() is old_value

    Note that the side effect of setx() happens immediately;
    __enter__() is a dummy returning self, __exit__() calls restore(),
    and if the object is GC'ed before restore() is called nothing
    happens.  Calling restore() a second time is a no-op.
    """

    def __init__(self, var: ContextVar, old_value: object, found: bool) -> None:
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
        new_ec = ExecutionContext(new_lc, ec.back, ec.depth)
        set_EC(new_ec)
        self._used = True

    def __enter__(self) -> 'CM':
        return self

    def __exit__(self, *args: Any) -> None:
        self.restore()

class FrozenDict(Mapping[KT, VT]):

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

    # API to create new FrozenDict instances.

    def add(self, key: KT, value: VT) -> 'FrozenDict[KT, VT]':
        d = dict(self.__d)
        d[key] = value
        return FrozenDict(d)

    def delete(self, key: KT) -> 'FrozenDict[KT, VT]':
        d = dict(self.__d)
        del d[key]
        return FrozenDict(d)

    def merge(self, other: 'FrozenDict[KT, VT]') -> 'FrozenDict[KT, VT]':
        # Note that for keys in both, self[key] prevails.
        d = dict(other.__d)
        d.update(self)
        return FrozenDict(d)

class LocalContext:
    """Mutable local context object.

    This wraps a FrozenDict.
    """

    _bare: FrozenDict[ContextVar, object]

    def __init__(self) -> None:
        self._bare = FrozenDict()

    def run_with_EC(self, ec: 'ExecutionContext', fn: Callable[..., T], *args: Any, **kwds: Any) -> T:
        """Run fn with this LC pushed on top of ec, then extract values back"""
        old_ec = get_EC()
        new_ec = ExecutionContext(self._bare, ec, ec.depth + 1)
        try:
            set_EC(new_ec)
            return fn(*args, **kwds)
        finally:
            self._bare = old_ec.lc
            set_EC(old_ec)

    def run(self, fn: Callable[..., T], *args: Any, **kwds: Any) -> T:
        """Run fn with this LC pushed on top of current EC, then extract values back"""
        old_ec = get_EC()
        return self.run_with_EC(old_ec, fn, *args, **kwds)

class ExecutionContext:
    """Execution context -- a linked list of FrozenDicts.

    To push a local context, use ExecutionContext(lc, ec).
    To pop a local context, use ec.back.
    """

    def __init__(self, lc: FrozenDict, back: Optional['ExecutionContext'], depth: int) -> None:
        self._lc = lc
        self._back = back
        self._depth = depth

    @property
    def depth(self) -> int:
        """Number of links in the chain (>= 1)"""
        return self._depth

    @property
    def lc(self) -> FrozenDict:
        return self._lc

    @property
    def back(self) -> Optional['ExecutionContext']:
        return self._back

    def vars(self) -> List[ContextVar]:
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
        return ExecutionContext(FrozenDict(lc), None, 1)

def run_with_EC(ec: ExecutionContext, fn: Callable[..., T], *args: Any, **kwds: Any) -> T:
    """Pushes given EC, calls callable, and pops the EC again"""
    new_lc = LocalContext()
    return new_lc.run_with_EC(ec, fn, *args, **kwds)
