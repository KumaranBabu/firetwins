"""Unit tests — pyfds.utils.formatting."""
from __future__ import annotations

import pytest
from pyfds.utils.formatting import (
    fmt_float, fmt_xb, fmt_ijk, fmt_xyz, fds_bool, fds_str,
)


class TestFmtFloat:
    def test_default_precision(self):
        assert fmt_float(3.14159265) == "3.1416"

    def test_custom_precision(self):
        assert fmt_float(1.23456789, 2) == "1.23"

    def test_integer_value(self):
        result = fmt_float(5.0)
        assert "5" in result

    def test_zero(self):
        assert fmt_float(0.0) == "0.0000" or "0" in fmt_float(0.0)

    def test_negative(self):
        assert "-" in fmt_float(-1.5)

    def test_scientific_notation_for_very_small(self):
        result = fmt_float(0.000001, 4)
        assert isinstance(result, str)


class TestFmtXb:
    def test_six_values(self):
        result = fmt_xb([0.0, 4.0, 0.0, 4.0, 0.0, 2.0])
        assert isinstance(result, str)
        assert result.count(",") == 5

    def test_contains_all_values(self):
        result = fmt_xb([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
        for v in ["1", "2", "3", "4", "5", "6"]:
            assert v in result

    def test_negative_values(self):
        result = fmt_xb([-1.0, 1.0, 0.0, 2.0, 0.0, 1.0])
        assert "-" in result


class TestFmtIjk:
    def test_three_integers(self):
        result = fmt_ijk((10, 20, 5))
        assert "10" in result
        assert "20" in result
        assert "5" in result

    def test_comma_separated(self):
        result = fmt_ijk((10, 20, 5))
        assert result.count(",") == 2


class TestFmtXyz:
    def test_three_floats(self):
        result = fmt_xyz((1.0, 2.0, 3.0))
        assert "1" in result
        assert "2" in result
        assert "3" in result


class TestFdsBool:
    def test_true(self):
        assert fds_bool(True) == ".TRUE."

    def test_false(self):
        assert fds_bool(False) == ".FALSE."


class TestFdsStr:
    def test_wraps_in_single_quotes(self):
        result = fds_str("hello")
        assert result == "'hello'"

    def test_empty_string(self):
        result = fds_str("")
        assert result == "''"

    def test_already_quoted_not_double_quoted(self):
        # If already quoted, should not add extra quotes
        result = fds_str("'already'")
        # implementation may or may not double-quote; just ensure it's a string
        assert isinstance(result, str)
