"""Snapshot comparison and the human/model-facing renderings of index status."""

from innieme.index_status import (
    FileStamp,
    IndexFreshness,
    IndexSnapshot,
    compare,
    describe_for_channel,
    describe_for_model,
    describe_names,
    format_age,
    format_duration,
    format_timestamp,
)


def _snapshot(files=None, failed=None, finished_at=1_000_000.0):
    return IndexSnapshot(
        started_at=finished_at - 4.2,
        finished_at=finished_at,
        extract_seconds=1.2,
        index_seconds=3.0,
        files=files or {},
        failed=failed or [],
        indexed_count=len(files or {}),
        chunk_count=12,
    )


# --- formatting -------------------------------------------------------------


def test_format_age_units():
    assert format_age(0) == "0s"
    assert format_age(59) == "59s"
    assert format_age(125) == "2m"
    assert format_age(3600) == "1h"
    assert format_age(3 * 3600 + 5 * 60) == "3h 5m"
    assert format_age(86400) == "1d"
    assert format_age(2 * 86400 + 4 * 3600) == "2d 4h"


def test_format_age_negative_is_zero():
    """Clock skew must not produce '-3s ago'"""
    assert format_age(-3) == "0s"


def test_format_duration():
    assert format_duration(4.23) == "4.2s"
    assert format_duration(0) == "0.0s"
    assert format_duration(-1) == "0.0s"
    assert format_duration(125) == "2m"


def test_format_timestamp_is_explicit_utc():
    assert format_timestamp(0) == "1970-01-01 00:00 UTC"


def test_snapshots_compare_by_identity():
    """A snapshot is the generation of its index; two scans are never equal"""
    a, b = _snapshot(), _snapshot()
    assert a == a and a != b
    assert len({a, b}) == 2


# --- compare ------------------------------------------------------------------


def test_compare_modified_new_removed(tmp_path):
    kept = tmp_path / "kept.md"
    kept.write_text("same")
    edited = tmp_path / "edited.md"
    edited.write_text("before")
    snap = _snapshot(
        files={
            str(kept): FileStamp.of(str(kept)),
            str(edited): FileStamp.of(str(edited)),
            str(tmp_path / "gone.md"): FileStamp(1, 1),
        }
    )
    edited.write_text("after, and longer")
    new = tmp_path / "new.md"
    new.write_text("x")

    fresh = compare(snap, [str(kept), str(edited), str(new)])
    assert fresh.modified == [str(edited)]
    assert fresh.added == [str(new)]
    assert fresh.removed == [str(tmp_path / "gone.md")]
    assert fresh.snapshot is snap
    assert fresh.stale_count == 3 and not fresh.is_current


def test_compare_unstattable_failed_file_becomes_modified_not_new(tmp_path):
    """A file that could not be stat'ed during the scan has no stamp"""
    f = tmp_path / "flaky.md"
    f.write_text("now readable")
    snap = _snapshot(files={}, failed=[str(f)])
    fresh = compare(snap, [str(f)])
    assert fresh.modified == [str(f)]
    assert fresh.added == []


def test_compare_failed_file_that_vanished_is_removed(tmp_path):
    snap = _snapshot(files={}, failed=[str(tmp_path / "gone.md")])
    assert compare(snap, []).removed == [str(tmp_path / "gone.md")]


# --- descriptions ---------------------------------------------------------------


def test_model_note_absent_without_snapshot_or_freshness():
    assert describe_for_model(None, None) == ""
    # Freshness could not be determined: the answer goes ahead without a note.
    assert describe_for_model(_snapshot(), None) == ""


def test_model_note_current():
    snap = _snapshot()
    note = describe_for_model(
        snap, IndexFreshness(0, snap), now=snap.finished_at + 3600
    )
    assert "last built" in note and "1h ago" in note
    assert "No source file has changed" in note


def test_model_note_stale_counts_only(tmp_path):
    snap = _snapshot()
    fresh = IndexFreshness(
        0, snap, modified=["/n/Northwind.md"], added=["/n/new.md"], removed=[]
    )
    note = describe_for_model(snap, fresh, now=snap.finished_at)
    assert "2 files changed since" in note
    assert "rescan" in note
    assert "not in the index" in note  # new files are absent, said so
    assert "Northwind" not in note and "new.md" not in note


def test_channel_status_counts_never_names():
    snap = _snapshot(failed=["/n/broken.pdf"])
    fresh = IndexFreshness(0, snap, modified=["/n/Northwind.md"])
    text = describe_for_channel("math", snap, fresh, now=snap.finished_at + 60)
    assert "1m ago" in text and "took 4.2s" in text
    assert "read 1.2s" in text and "index 3.0s" in text
    assert "12 chunks" in text
    assert "Could not be read: 1 file" in text
    assert "1 file changed since" in text and "rescan" in text
    assert "Northwind" not in text and "broken" not in text


def test_channel_status_before_any_scan():
    assert "No scan has completed yet" in describe_for_channel("math", None, None)


def test_channel_status_freshness_unavailable_still_gives_scan_details():
    snap = _snapshot()
    text = describe_for_channel("math", snap, None, freshness_unavailable=True)
    assert "12 chunks" in text
    assert "could not be determined" in text


def test_names_group_and_quote(tmp_path):
    snap = _snapshot(failed=[str(tmp_path / "bad.pdf")])
    fresh = IndexFreshness(
        0,
        snap,
        modified=[str(tmp_path / "sub" / "a.md")],
        added=[str(tmp_path / "b.md")],
        removed=[str(tmp_path / "c.md")],
    )
    text = describe_names(snap, fresh, str(tmp_path), quote=lambda s: f"[{s}]")
    lines = text.splitlines()
    assert lines[1:] == [
        "Could not be read:",
        "  - [bad.pdf]",
        "Modified:",
        "  - [sub/a.md]",
        "New:",
        "  - [b.md]",
        "Removed:",
        "  - [c.md]",
    ]


def test_names_none_when_nothing_to_name():
    snap = _snapshot()
    assert describe_names(snap, IndexFreshness(0, snap), "/n", quote=str) is None
    assert describe_names(None, None, "/n", quote=str) is None


def test_names_truncate_long_lists():
    snap = _snapshot()
    fresh = IndexFreshness(0, snap, modified=[f"/n/{i:02d}.md" for i in range(25)])
    text = describe_names(snap, fresh, "/n", quote=str, limit=20)
    assert text.splitlines()[-1] == "  - and 5 more"


def test_compare_still_unstattable_failed_file_is_not_an_error(tmp_path, monkeypatch):
    """Unstat-able at scan time and still: no change, and no check failure"""
    import innieme.index_status as mod

    path = str(tmp_path / "locked.md")
    snap = _snapshot(files={}, failed=[path])

    def deny(p):
        raise PermissionError(p)

    monkeypatch.setattr(mod.os, "stat", deny)
    fresh = compare(snap, [path])
    assert fresh.is_current
    assert compare(snap, []).is_current
