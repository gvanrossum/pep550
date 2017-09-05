# Stub for PEP 550.  Names subject to bikeshedding.

from typing import *

T = TypeVar('T')
S = TypeVar('S')

class ContextVar(Generic[T, S]):
    """Context variable."""
    def __init__(self, *, description: str, default: S) -> None: ...
    @property
    def description(self) -> str: ...
    @property
    def default(self) -> S: ...
    # Methods that take the current context into account
    def get(self) -> Union[T, S]: ...  # Return topmost value or default
    def set(self, value: T) -> None: ...  # Overwrite topmost value
    def setx(self, value: T) -> _CM: ...  # Overwrite topmost value, allows restore()

class _CM:
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
    def restore(self) -> None: ...
    def __enter__(self) -> CM: ...
    def __exit__(self, *args: Any) -> None: ...

class BareLocalContext:
    # Do we want to implement Mapping?
    """Immutable local context object.

    This is implemented as a HAMT (hash tree).
    """
    def __getitem__(self, var: ContextVar[T, S]) -> Union[T, S]: ...
    def assign(self, var: ContextVar[T, S], value: T) -> BareLocalontext: ...
    def unassign(self, var: ContextVar[T, S]) -> BareLocalontext: ...
    def merge(self, other: BareLocalontext) -> BareLocalontext: ...
    # Do we want keys(), __len__()?
    def run(self, fn: Callable[..., T], *args: Any, **kwds: Any) -> T: ...

class WrappedLocalContext:
    """Mutable local context object.

    This wraps a BareLocalContext.
    """
    @property
    def lc(self) -> BareLocalContext: ...  # return self._lc
    def run(self, fn: Callable[..., T], *args: Any, **kwds: Any) -> T:
        orig_ec = getEC()
        ec = ExecutionContext(lc, orig_ec)
        try:
            return fn(*args, **kwds)
        finally:
            self._lc = ec.lc
            setEC(orig_ec)

class ExecutionContext:
    """Execution context -- a linked list of BareLocalContexts.

    To push a local context, use ExecutionContext(lc, ec).
    To pop a local context, use ec.back.
    """
    def __init__(self, lc: BareLocalContexts, back: Optional[ExecutionContext]) -> None: ...
    @property
    def depth(self) -> int: ...
    @property
    def lc(self) -> BareLocalContext: ...
    @property
    def back(self) -> ExecutionContext: ...
    def run(self, fn: Callable[..., T], *args, **kwds) -> T: ...  # Pushes empty LC and calls callable

def getEC() -> ExecutionContext: ...  # Return current thread's EC
def setEC(ec: ExecutionContext) -> None: ...  # Set current thread's EC
