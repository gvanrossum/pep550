# Stub for PEP 550.  Names subject to bikeshedding.

from typing import *

T = TypeVar('T')
S = TypeVar('S')

class ContextVar(Generic[T, S]):
    """Context variable."""

    def __init__(self, *, name: str, default: S) -> None:
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
        ec = get_EC()
        while ec is not None:
            try:
                # NOTE: Split in two halves to work around mypy issue
                v = ec.lc[self]
                return v
            except KeyError:
                ec = ec.back
        return self._default

    def set(self, value: T) -> None:
        """Overwrite topmost value"""
        ec = get_EC()
        lc = ec.lc
        new_lc = lc.assign(self, value)
        new_ec = ExecutionContext(new_lc, ec.back)
        set_EC(new_ec)

    def setx(self, value: T) -> CM:
        """Overwrite topmost value, allows restore()"""
        ec = get_EC()
        lc = ec.lc
        try:
            orig = lc[self]
            found = True
        except KeyError:
            orig = None
            found = False
        new_lc = lc.assign(self, value)
        new_ec = ExecutionContext(new_lc, ec.back)
        set_EC(new_ec)
        return CM(self, orig, found)

class CM:
    """Context manager for restoring a ContextVar's previous state.

    var = ContextVar(...)

    def fun():
        orig = var.get()
        with var.setx(<value>):
            <stuff>
        assert var.get() is orig

    Note that the side effect of setx() happens immediately;
    __enter__() is a dummy returning self, __exit__() calls restore(),
    and if the object is GC'ed before restore() is called nothing
    happens.  Calling restore() a second time is a no-op.
    """

    def __init__(self, var: ContextVar, orig: object, found: bool) -> None:
        self._var = var
        self._orig = orig
        self._found = found
        self._used = False

    def restore(self) -> None:
        if self._used:
            return
        ec = get_EC()
        lc = ec.lc
        if self._found:
            new_lc = lc.assign(self._var, self._orig)
        else:
            new_lc = lc.unassign(self._var)
        new_ec = ExecutionContext(new_lc, ec.back)
        set_EC(new_ec)
        self._used = True

    def __enter__(self) -> CM:
        return self

    def __exit__(self, *args: Any) -> None:
        self.restore()

class BareLocalContext:
    # Do we want to implement Mapping?
    """Immutable local context object.

    This is implemented as a HAMT (hash tree).
    """
    def __getitem__(self, var: ContextVar[T, S]) -> Union[T, S]: ...
    def assign(self, var: ContextVar[T, S], value: T) -> BareLocalContext: ...
    def unassign(self, var: ContextVar[T, S]) -> BareLocalContext: ...
    def merge(self, other: BareLocalContext) -> BareLocalContext: ...
    # Do we want keys(), __len__()?
    def run(self, fn: Callable[..., T], *args: Any, **kwds: Any) -> T: ...

class WrappedLocalContext:
    """Mutable local context object.

    This wraps a BareLocalContext.
    """
    @property
    def lc(self) -> BareLocalContext: ...  # return self._lc
    def run(self, fn: Callable[..., T], *args: Any, **kwds: Any) -> T:
        orig_ec = get_EC()
        ec = ExecutionContext(self.lc, orig_ec)
        try:
            return fn(*args, **kwds)
        finally:
            self._lc = ec.lc
            set_EC(orig_ec)

class ExecutionContext:
    """Execution context -- a linked list of BareLocalContexts.

    To push a local context, use ExecutionContext(lc, ec).
    To pop a local context, use ec.back.
    """

    def __init__(self, lc: BareLocalContext, back: Optional[ExecutionContext]) -> None:
        self._lc = lc
        self._back = back

    @property
    def depth(self) -> int:
        """Number of links in the chain (>= 1)"""
        if self.back is None:
            return 1
        return self.back.depth + 1

    @property
    def lc(self) -> BareLocalContext:
        return self._lc

    @property
    def back(self) -> ExecutionContext:
        return self._back

    def squash(self) -> ExecutionContext: ...  # Return an equivalent EC with depth 1

def get_EC() -> ExecutionContext: ...  # Return current thread's EC

def set_EC(ec: ExecutionContext) -> None: ...  # Set current thread's EC

def run_with_EC(fn: Callable[..., T], *args, **kwds) -> T:
    """Pushes empty LC and calls callable"""
    ec = get_EC()
    try:
        set_EC(ExecutionContext(BareLocalContext(), ec))
        return fn(*args, **kwds)
    finally:
        set_EC(ec)
