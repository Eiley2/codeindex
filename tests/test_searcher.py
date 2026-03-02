from __future__ import annotations

from pathlib import Path

from codeindex import searcher


def test_extract_line_range_from_nested_mapping() -> None:
    location = {"start": {"line": 21, "column": 1}, "end": {"line": 27, "column": 4}}
    assert searcher._extract_line_range(location) == (21, 27)


def test_extract_line_range_from_json_string() -> None:
    location = '{"line_start": "8", "line_end": "10"}'
    assert searcher._extract_line_range(location) == (8, 10)


def test_extract_line_range_without_line_metadata_returns_none() -> None:
    assert searcher._extract_line_range({"offset": 123, "length": 55}) == (None, None)


def test_extract_offset_range_from_dict() -> None:
    assert searcher._extract_offset_range({"offset_start": 11, "offset_end": 29}) == (11, 29)


def test_attach_line_numbers_from_offsets(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    target = repo / "app.py"
    target.write_text("first line\nsecond line\nthird line\n", encoding="utf-8")

    result = searcher.SearchResult(
        rank=1,
        score=0.99,
        filename="app.py",
        text="second line\nthird line",
        offset_start=11,
        offset_end=32,
    )
    searcher.attach_line_numbers([result], repo)

    assert result.line_start == 2
    assert result.line_end == 3
