(Scrachpad for some thoughts about PEP 550.)

Abstract
========

This PEP proposes new APIs and changes to the interpreter and stdlib
to support context variables.  This is a concept similar to
thread-local variables but allows correctly keeping track of values
per task (e.g. ``asyncio.Task``).  The PEP also propose changes to
generators and coroutines to correctly context variables upon entering
and leaving those, and suggests changes to e.g. the ``decimal`` module
to make use of the new mechanism.  Two parallel APIs are proposed: one
for use from Python code, and another for use from C code.  Most of
the PEP's explanation focuses on the Python API.

Introduction
============

The PEP proposes a new mechanism for managing context variables.  The
key classes involved in this mechanism are ``ExecutionContext``,
``LocalContext`` and ``ContextVar``; all will be explained below.  The
PEP also proposes some policies for using the mechanism around
generators, coroutines and tasks.

The proposed mechanism for accessing context variables uses the
``ContextVar`` class.  A module (such as ``decimal``) that wishes to
store a context variable should:

- declare a module-global variable holding a ``ContextVar`` to serve
  as a "key"

- access the current value via the ``get()`` method on the key
  variable

- modify the current value via the ``set()`` and ``setx()`` methods on
  the key variable

The notion of "current value" deserves special consideration:
different tasks, coroutines, generators and threads that exist (and
execute) concurrently may have different values.  This idea is
well-known from thread-local storage but in this case the locality of
the value is not always necessarily to a thread.  Instead, there is
the notion of the "current ``ExecutionContext``" which is stored in
thread-local storage.

An ``ExecutionContext`` is similar to a ``ChainMap`` but the
underlying mappings are immutable.  The ``ContextVar.get()`` method
does a lookup with ``self`` as a key, returning ``None`` if the search
falls through.  The ``ExecutionContext`` itself is implemented as an
immutable linked list, where each node has a pointer to the underlying
immutable mapping and a back pointer (to the following link in the
chain).

The ``ContextVar.set()`` method always updates the mapping at the
front link of the current ``ExecutionContext`` chain.  It does this by
making a new immutable mapping, then making a new chain link to
replace the current one, and finally making the new chain link into
the current ``ExecutionContext`` for the current thread.

The ``ContextVar.setx()`` method is similar to ``ContextVar.set()``
but returns a context manager whose ``__exit__()`` method restores the
previous state of that context variable in the current
``ExecutionContext`` by either overwriting it with its previous value
or deleting it (if the previous value did not originate in the front
of the chain).

Rationale
=========

- We all know that thread-local variables are insufficient when using
  tasks.

- Specifically, the problem is that when a context manager is used to
  save and restore a context variable, the saved value can bleed into
  another task whenever the task uses ``await`` to wait for some event
  to happen.

- There are also problems with generators, where again a context
  manager saving and restoring values may cause the value to bleed
  into other code unexpectedly.

- The simplest solution would be to have a "current environment",
  which would be a dict associated with a task or generator.  This
  would just be a mutable dict.  ``ContextVar`` methods would get the
  current environment and read or modify it.  Tasks would choose some
  initial environment when they are created, and whenever a task is
  activated its environment would be made current, and when the task
  blocks, the previous environment would be made current again.

- Manipulation of the current environment would be up to the task
  framework, e.g. asyncio or trio.

- The choices for the initial environment for a task are pretty much
  (a) start with a blank slate (like threading.local) or (b) inherit
  from the parent.  Strong arguments for (b) exist, e.g. the desire of
  certain web frameworks to maintain a "tracing ID" across tasks.  But
  in the end this is up to the framework.  The PEP proposes (b) for
  asyncio.

Another way to present it
-------------------------

1. This problem deserves to be solved for tasks (and coroutines).

2. The problem also exists for generators.

3. Why should the initial environment for tasks be cloned?
   E.g. tracing IDs.

4. Why should the environment be immutable?  Because cloning a mutable
   dict is expensive, but cloning an immutable one is O(1).

5. Why do we need a stack of immutable mappings?  Well, v1 doesn't
   need a stack; it captures the environment when the generator object
   is created.  But Nathaniel found a use case that v1 doesn't solve
   (something to do with using with-statements to set timeouts, and
   expecting timeouts to affect generators resumed inside such
   with-statements), and proposed v2, which uses a stack -- it doesn't
   capture anything, but creates an empty immutable dict when the
   generator is created; this is pushed on top of the stack whenever
   the generator is resumed, and popped back off whenever the
   generator yields or exits.  (The top immutable dict can be modified
   in the generator code, and its latest version is stored into the
   generator object when it is popped.)  See Nathaniel's email
   [https://mail.python.org/pipermail/python-ideas/2017-August/046736.html]
   point 9.

6. Why do we use a HAMT implementation?  It seems to be the only
   efficiently updatable immutable hash table implementation.

(Probably more.)
