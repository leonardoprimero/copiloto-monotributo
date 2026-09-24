"""Where the graph keeps its checkpoints.

`interrupt()` needs a checkpointer, and which one decides how long a paused
case lives. In memory, it lives as long as the process: fine for a CLI that
asks and resumes in one sitting. On disk, it lives until someone resumes it,
which is what lets an accountant pick a case up hours later from another
process.

Both savers use this project's serializer, so a state written before a pause
comes back with its own types rather than as plain dictionaries.
"""

import sqlite3
from pathlib import Path

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver

from copiloto.graph.serde import copilot_serde


def open_checkpointer(path: Path | None) -> BaseCheckpointSaver:
    """An in-memory saver without a path; a SQLite saver on `path` with one.

    The connection allows use from other threads because a web server handles
    each request on its own thread and the saver serializes access with its
    own lock, as `SqliteSaver.from_conn_string` does.
    """
    if path is None:
        return InMemorySaver(serde=copilot_serde())

    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path), check_same_thread=False)
    return SqliteSaver(connection, serde=copilot_serde())
