"""What the index knows about itself: when it was built, from which files, and
whether those files have changed since.

The index is a snapshot. Nothing in the vector store says when it was taken or
what it was taken from, so neither the bot nor the people asking it can tell a
note that is current from one edited after the last scan. ``IndexSnapshot``
records that at scan time; ``IndexFreshness`` is the result of comparing it with
the directory as it is now, using ``stat`` only -- no re-reading, no embedding.
"""

import os
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional


@dataclass(frozen=True)
class FileStamp:
    """A file's identity for staleness purposes.

    mtime plus size is deliberately all there is: hashing would mean reading
    every file on every check, and a note edited by the maintenance process
    changes one or both.
    """

    mtime_ns: int
    size: int

    @classmethod
    def of(cls, path: str) -> Optional["FileStamp"]:
        """The file's current stamp, or None if it cannot be stat'ed."""
        try:
            st = os.stat(path)
        except OSError:
            return None
        return cls(mtime_ns=st.st_mtime_ns, size=st.st_size)


@dataclass
class IndexSnapshot:
    """One completed scan.

    ``files`` holds the stamp of every non-excluded candidate the scan looked
    at, taken *before* the file was read. A file edited mid-scan then compares
    as changed, rather than being recorded with a stamp newer than the text that
    was actually indexed.
    """

    started_at: float  # epoch seconds
    finished_at: float
    extract_seconds: float  # reading and parsing the documents
    index_seconds: float  # chunking, embedding and building the store
    files: Dict[str, FileStamp]
    failed: List[str]  # paths whose text could not be extracted
    indexed_count: int  # files that contributed text
    chunk_count: int

    @property
    def duration(self) -> float:
        return self.extract_seconds + self.index_seconds


@dataclass
class IndexFreshness:
    """How the directory differs from the snapshot. Paths are as globbed."""

    checked_at: float
    modified: List[str] = field(default_factory=list)
    added: List[str] = field(default_factory=list)
    removed: List[str] = field(default_factory=list)

    @property
    def stale_count(self) -> int:
        return len(self.modified) + len(self.added) + len(self.removed)

    @property
    def is_current(self) -> bool:
        return self.stale_count == 0

    @property
    def changed_sources(self) -> frozenset:
        """Paths whose indexed text may no longer match the file.

        Added files are not here: they have no chunks, so no retrieved chunk can
        come from one.
        """
        return frozenset(self.modified) | frozenset(self.removed)


def format_age(seconds: float) -> str:
    """A duration as the two most significant units: ``45s``, ``3h 5m``."""
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    minutes, _ = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m"
    hours, minutes = divmod(minutes, 60)
    if hours < 24:
        return f"{hours}h {minutes}m" if minutes else f"{hours}h"
    days, hours = divmod(hours, 24)
    return f"{days}d {hours}h" if hours else f"{days}d"


def format_duration(seconds: float) -> str:
    """A scan's runtime: sub-minute values keep a decimal, longer ones do not."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    return format_age(seconds)


def format_timestamp(epoch: float) -> str:
    """UTC, explicitly: the model and the channel may not share a time zone."""
    return time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(epoch))


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def _freshness_counts(freshness: IndexFreshness) -> str:
    return (
        f"{freshness.stale_count} changed since "
        f"({len(freshness.modified)} modified, "
        f"{len(freshness.added)} new, {len(freshness.removed)} removed)"
    )


def describe_for_model(
    snapshot: Optional[IndexSnapshot],
    freshness: Optional[IndexFreshness],
    now: Optional[float] = None,
) -> str:
    """The note placed in the system prompt so the model can speak to staleness.

    Counts only. Which files changed matters to the model only for the chunks it
    was handed, and those are labelled individually (see ``_format_chunk``).
    """
    if snapshot is None:
        return ""
    now = time.time() if now is None else now
    line = (
        f"Document index last built {format_timestamp(snapshot.finished_at)} "
        f"({format_age(now - snapshot.finished_at)} ago)."
    )
    if freshness is None:
        return line
    if freshness.is_current:
        return f"{line} No source file has changed since."
    return (
        f"{line} {_freshness_counts(freshness)}. Excerpts marked as changed "
        "since indexing may be out of date, and a new file's contents are not "
        "in the index at all. Where that could affect the answer, say so and "
        "suggest a rescan (mentioning the bot with the word `rescan`) rather "
        "than presenting the excerpt as current."
    )


def describe_for_channel(
    topic: str,
    snapshot: Optional[IndexSnapshot],
    freshness: Optional[IndexFreshness],
    docs_dir: str,
    show_names: bool,
    now: Optional[float] = None,
    quote: Callable[[str], str] = lambda s: f"`{s}`",
) -> str:
    """The ``status`` reply.

    Counts for everyone. Filenames only when ``show_names`` is set: this is
    posted in a channel anyone can read, and the same discretion that keeps
    excluded files out of the startup message applies to files not yet indexed.
    ``quote`` renders a name safely for the target platform.
    """
    if snapshot is None:
        return f"*Index status for {topic}*\nNo scan has completed yet."
    now = time.time() if now is None else now

    def rel(path: str) -> str:
        try:
            return os.path.relpath(path, docs_dir)
        except ValueError:
            return os.path.basename(path)

    def names(paths: List[str], limit: int = 10) -> str:
        shown = ", ".join(quote(rel(p)) for p in sorted(paths)[:limit])
        extra = len(paths) - limit
        return f"{shown}, and {extra} more" if extra > 0 else shown

    lines = [
        f"*Index status for {topic}*",
        f"• Last scan: {format_timestamp(snapshot.finished_at)} "
        f"({format_age(now - snapshot.finished_at)} ago), took "
        f"{format_duration(snapshot.duration)} "
        f"(read {format_duration(snapshot.extract_seconds)}, "
        f"index {format_duration(snapshot.index_seconds)})",
        f"• Indexed: {_plural(snapshot.chunk_count, 'chunk')} from "
        f"{_plural(snapshot.indexed_count, 'file')}",
    ]
    if snapshot.failed:
        line = f"• Could not be read: {len(snapshot.failed)}"
        if show_names:
            line += f" ({names(snapshot.failed)})"
        lines.append(line)

    if freshness is None:
        lines.append("• Freshness: not checked")
    elif freshness.is_current:
        lines.append("• Freshness: up to date, no source file has changed since the scan")
    else:
        lines.append(f"• Freshness: {_freshness_counts(freshness)}")
        if show_names:
            for label, paths in (
                ("Modified", freshness.modified),
                ("New", freshness.added),
                ("Removed", freshness.removed),
            ):
                if paths:
                    lines.append(f"    {label}: {names(paths)}")
        lines.append("• Run a `rescan` to pick the changes up.")
    return "\n".join(lines)
