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
from typing import Any, Callable, Dict, List, Optional


@dataclass(frozen=True)
class FileStamp:
    """A file's identity for staleness purposes.

    mtime plus size is deliberately all there is: hashing would mean reading
    every file on every check, and a note rewritten by the maintenance process
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


@dataclass(frozen=True, eq=False)
class IndexSnapshot:
    """One completed scan.

    ``files`` holds the stamp of every non-excluded candidate the scan looked
    at, taken *before* the file was read, so a file edited mid-scan compares as
    changed afterwards. A candidate that could not be stat'ed is in ``failed``
    and has no stamp. Frozen, and compared by identity: a snapshot *is* the
    generation of the index it was published with.
    """

    started_at: float  # epoch seconds
    finished_at: float
    extract_seconds: float  # reading and parsing the documents
    index_seconds: float  # chunking, embedding and building the store
    files: Dict[str, FileStamp]
    failed: List[str]
    indexed_count: int  # files that contributed text
    chunk_count: int

    @property
    def duration(self) -> float:
        return self.extract_seconds + self.index_seconds


@dataclass(frozen=True, eq=False)
class PublishedIndex:
    """A vector store together with the snapshot that describes it.

    Published as one object so a reader can never see one without the other:
    excerpts retrieved from ``store`` are judged against ``snapshot``, even if
    a rescan publishes a newer pair while the answer is being prepared.
    """

    store: Any
    snapshot: Optional[IndexSnapshot]


@dataclass(frozen=True)
class ScanResult:
    """What one scan produced: the channel message and its own snapshot."""

    message: str
    snapshot: IndexSnapshot


@dataclass
class IndexFreshness:
    """How the directory differs from one snapshot. Paths are as discovered."""

    checked_at: float
    snapshot: Optional[IndexSnapshot] = None
    modified: List[str] = field(default_factory=list)
    added: List[str] = field(default_factory=list)
    removed: List[str] = field(default_factory=list)

    @property
    def stale_count(self) -> int:
        return len(self.modified) + len(self.added) + len(self.removed)

    @property
    def is_current(self) -> bool:
        return self.stale_count == 0


class FreshnessUnavailable(Exception):
    """An explicit freshness check could not finish (error or time limit)."""


def _stat_or_absent(path: str) -> Optional[FileStamp]:
    """The file's stamp, or None if it does not exist.

    Any other failure (permissions, an I/O error on the mount) raises: "I could
    not look" must not be reported as "unchanged" or "deleted".
    """
    try:
        st = os.stat(path)
    except (FileNotFoundError, NotADirectoryError):
        return None
    return FileStamp(mtime_ns=st.st_mtime_ns, size=st.st_size)


def compare(snapshot: IndexSnapshot, current: List[str]) -> IndexFreshness:
    """Compare the candidate files found now with a snapshot, by ``stat`` alone.

    Every file recorded in the snapshot is compared -- indexed, empty and
    failed alike -- so an empty file that gains text, or a failed file that is
    repaired, shows up. A failed file that could not be stat'ed during the scan
    has no stamp; once it can be, it counts as modified rather than new.

    Raises OSError when a file cannot be examined, including one the directory
    walk could not see (glob silently skips directories it cannot read) but
    that still exists: the caller reports freshness as unknown instead.
    """
    freshness = IndexFreshness(checked_at=time.time(), snapshot=snapshot)
    failed = set(snapshot.failed)
    seen = set()
    for path in current:
        try:
            stamp = _stat_or_absent(path)
        except OSError:
            if path in failed and path not in snapshot.files:
                # Unstat-able at scan time and still: nothing has changed.
                seen.add(path)
                continue
            raise
        if stamp is None:
            continue  # deleted since the walk: handled as removed below
        seen.add(path)
        recorded = snapshot.files.get(path)
        if recorded is None:
            (freshness.modified if path in failed else freshness.added).append(path)
        elif stamp != recorded:
            freshness.modified.append(path)
    for path in sorted((set(snapshot.files) | failed) - seen):
        try:
            present = _stat_or_absent(path) is not None
        except OSError:
            if path in failed and path not in snapshot.files:
                continue  # still unreadable, as at scan time
            raise
        if present:
            raise OSError(f"could not enumerate the directory holding {path}")
        freshness.removed.append(path)
    return freshness


def format_age(seconds: float) -> str:
    """A duration as its two most significant units: ``45s``, ``3h 5m``."""
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m"
    hours, minutes = divmod(minutes, 60)
    if hours < 24:
        return f"{hours}h {minutes}m" if minutes else f"{hours}h"
    days, hours = divmod(hours, 24)
    return f"{days}d {hours}h" if hours else f"{days}d"


def format_duration(seconds: float) -> str:
    """A scan's runtime: sub-minute values keep a decimal, longer ones do not."""
    seconds = max(0.0, seconds)
    if seconds < 60:
        return f"{seconds:.1f}s"
    return format_age(seconds)


def format_timestamp(epoch: float) -> str:
    """UTC, explicitly: the model and the channel may not share a time zone."""
    return time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(epoch))


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def _counts(freshness: IndexFreshness) -> str:
    return (
        f"{_plural(freshness.stale_count, 'file')} changed since "
        f"({len(freshness.modified)} modified, {len(freshness.added)} new, "
        f"{len(freshness.removed)} removed)"
    )


def describe_for_model(
    snapshot: Optional[IndexSnapshot],
    freshness: Optional[IndexFreshness],
    now: Optional[float] = None,
) -> str:
    """The note placed in the model's context so it can speak to staleness.

    Counts only: the model learns which files changed only through the labels
    on excerpts it was handed. Empty before the first scan, and when freshness
    could not be determined -- the answer then goes ahead without it.
    """
    if snapshot is None or freshness is None:
        return ""
    now = time.time() if now is None else now
    line = (
        f"Document index last built {format_timestamp(snapshot.finished_at)} "
        f"({format_age(now - snapshot.finished_at)} ago)."
    )
    if freshness.is_current:
        return f"{line} No source file has changed since."
    note = (
        f"{line} {_counts(freshness)}. Excerpts labelled as changed since "
        "indexing, or as no longer existing, may be out of date. Where that "
        "could affect the answer, say so and suggest a rescan (mentioning the "
        "bot with the word `rescan`) rather than presenting them as current."
    )
    if freshness.added:
        note += (
            " New files are not in the index at all, so their contents are absent here."
        )
    return note


def describe_for_channel(
    topic: str,
    snapshot: Optional[IndexSnapshot],
    freshness: Optional[IndexFreshness],
    freshness_unavailable: bool = False,
    now: Optional[float] = None,
) -> str:
    """The ``status`` reply posted in the channel. Counts only, never names.

    Everyone in the channel sees this, and it is read back into the model's
    conversation history, so file names go separately and privately
    (``describe_names``).
    """
    if snapshot is None:
        return f"*Index status for {topic}*\nNo scan has completed yet."
    now = time.time() if now is None else now
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
        lines.append(f"• Could not be read: {_plural(len(snapshot.failed), 'file')}")
    if freshness_unavailable or freshness is None:
        lines.append("• Freshness: could not be determined right now")
    elif freshness.is_current:
        lines.append(
            "• Freshness: up to date, no source file has changed since the scan"
        )
    else:
        lines.append(f"• Freshness: {_counts(freshness)}")
        lines.append("• Run a `rescan` to pick the changes up.")
    return "\n".join(lines)


def describe_names(
    snapshot: Optional[IndexSnapshot],
    freshness: Optional[IndexFreshness],
    docs_dir: str,
    quote: Callable[[str], str],
    limit: int = 20,
) -> Optional[str]:
    """The file names behind the ``status`` counts, for the outie only.

    None when there is nothing to name. ``quote`` renders a name safely for the
    target platform; names are untrusted text.
    """
    if snapshot is None:
        return None

    def rel(path: str) -> str:
        try:
            return os.path.relpath(path, docs_dir)
        except ValueError:  # different drive on Windows
            return os.path.basename(path)

    def names(paths: List[str]) -> List[str]:
        # One name per line: a long report can then be split at line breaks
        # without ever cutting a name.
        shown = [f"  - {quote(rel(p))}" for p in sorted(paths)[:limit]]
        extra = len(paths) - limit
        return shown + ([f"  - and {extra} more"] if extra > 0 else [])

    groups = [("Could not be read", snapshot.failed)]
    if freshness is not None:
        groups += [
            ("Modified", freshness.modified),
            ("New", freshness.added),
            ("Removed", freshness.removed),
        ]
    lines: List[str] = []
    for label, paths in groups:
        if paths:
            lines.append(f"{label}:")
            lines.extend(names(paths))
    if not lines:
        return None
    return "Files behind the status counts (only you can see this):\n" + "\n".join(
        lines
    )
