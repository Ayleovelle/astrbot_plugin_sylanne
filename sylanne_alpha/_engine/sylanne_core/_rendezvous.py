"""Process-global rendezvous cell for SylanneEngine sharing.

Vendored copies of sylanne_core can live under different module names
(e.g. ``pluginA.deps.sylanne_core`` vs ``pluginB.deps.sylanne_core``), each with
its own module globals. Without a shared meeting point they would each keep a
private engine registry and could build two engines for one data_dir — racing on
flush and losing updates.

The cell fixes that: it is a single object published in the ``builtins`` namespace
under a fixed sentinel key identical in every copy. ``builtins`` is interpreter-
global and never vendored, so every copy — whatever its import name — converges on
ONE registry and dedups for real. There is no election and no master handoff here:
the first caller builds the engine, it stays put for the process lifetime, and
upgrades happen by restart.

The cell is a deliberately dumb, append-only shelf; ALL policy lives in the
per-copy SDK, so "the first copy to build the cell wins its shape" is harmless.
``get_cell`` fills any field a newer copy expects but an older builder omitted.
"""

from __future__ import annotations

import builtins
import threading
from typing import Any, cast

# The "_v1" suffix is a schema version: only a forced layout break bumps it, so an
# incompatible future cell coexists instead of corrupting this one.
_RENDEZVOUS_KEY = "__sylanne_core_rendezvous_v1__"

# The lazy field-fill in get_cell is serialized by a PROCESS-global lock (also in
# builtins): a module-level lock would be distinct per vendored copy and would not
# mutually exclude copies racing to fill fields on the one shared cell.
_BOOTSTRAP_KEY = "__sylanne_core_bootstrap_lock_v1__"


class _Cell:
    """Process-global shelf shared by every loaded sylanne_core copy.

    - ``lock``: guards all mutations of the dicts below.
    - ``registry``: data_dir key -> live _Entry or in-flight asyncio.Future tombstone.
    - ``identities``: copy_id -> identity record of every copy that has registered.
    - ``builders``: data_dir key -> copy_id of the copy that built that engine.
    """

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.registry: dict[str, Any] = {}
        self.identities: dict[str, Any] = {}
        self.builders: dict[str, str] = {}


def get_cell() -> _Cell:
    """Return the one process-global cell, creating it on first use.

    ``dict.setdefault`` is atomic under the GIL, so concurrent first-callers all
    receive the single winner; the losers' candidate cells are discarded.
    """
    cell = builtins.__dict__.get(_RENDEZVOUS_KEY)
    if cell is None:
        cell = builtins.__dict__.setdefault(_RENDEZVOUS_KEY, _Cell())
    # Tolerate a cell built by a different SDK version that predates a field: fill
    # whatever this version needs. Cheap, and race-safe under a process-global lock.
    if not all(hasattr(cell, n) for n in ("lock", "registry", "identities", "builders")):
        bootstrap = builtins.__dict__.setdefault(_BOOTSTRAP_KEY, threading.Lock())
        with bootstrap:
            if not hasattr(cell, "lock"):
                cell.lock = threading.Lock()
            for name in ("registry", "identities", "builders"):
                if not hasattr(cell, name):
                    setattr(cell, name, {})
    return cast("_Cell", cell)
