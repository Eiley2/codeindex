from __future__ import annotations

from codeindex import searcher


def test_extract_line_range_from_nested_mapping() -> None:
    location = {"start": {"line": 21, "column": 1}, "end": {"line": 27, "column": 4}}
    assert searcher._extract_line_range(location) == (21, 27)


def test_extract_line_range_from_json_string() -> None:
    location = '{"line_start": "8", "line_end": "10"}'
    assert searcher._extract_line_range(location) == (8, 10)


def test_extract_line_range_without_line_metadata_returns_none() -> None:
    assert searcher._extract_line_range({"offset": 123, "length": 55}) == (None, None)
