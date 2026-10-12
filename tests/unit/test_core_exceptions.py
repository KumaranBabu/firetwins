"""Unit tests — pyfds.core.exceptions."""
from __future__ import annotations

import pytest
from pyfds.core.exceptions import (
    FdsError, FdsValidationError, FdsExecutionError, FdsParseError,
    FdsSerializationError, FdsPluginError, FdsConfigError,
    FdsJobError, FdsNotFoundError, FdsTimeoutError, FdsBinaryError,
)


class TestFdsError:
    def test_basic_message(self):
        e = FdsError("something failed")
        assert str(e) == "something failed"

    def test_context_appears_in_str(self):
        e = FdsError("boom", context="myfile.fds")
        assert "context: myfile.fds" in str(e)

    def test_no_context(self):
        e = FdsError("boom")
        assert "context" not in str(e)

    def test_is_exception_subclass(self):
        with pytest.raises(FdsError):
            raise FdsError("test")


class TestFdsValidationError:
    def test_errors_list_stored(self):
        e = FdsValidationError("invalid", errors=["e1", "e2"])
        assert e.errors == ["e1", "e2"]

    def test_errors_in_str(self):
        e = FdsValidationError("invalid", errors=["no mesh defined"])
        assert "no mesh defined" in str(e)

    def test_empty_errors_list(self):
        e = FdsValidationError("invalid")
        assert e.errors == []

    def test_is_fds_error(self):
        assert isinstance(FdsValidationError("x"), FdsError)


class TestFdsExecutionError:
    def test_returncode_in_str(self):
        e = FdsExecutionError("FDS failed", returncode=1)
        assert "returncode=1" in str(e)

    def test_stderr_truncated_in_str(self):
        e = FdsExecutionError("crash", stderr="a" * 300)
        s = str(e)
        assert "stderr=" in s
        # repr shows up to 200 chars of stderr
        assert len(s) < 400

    def test_no_returncode_or_stderr(self):
        e = FdsExecutionError("crash")
        assert str(e) == "crash"


class TestFdsParseError:
    def test_filepath_stored(self):
        e = FdsParseError("bad line", filepath="bad.fds")
        assert e.filepath == "bad.fds"

    def test_line_number_in_str(self):
        e = FdsParseError("bad line", filepath="bad.fds", line_number=42)
        assert "42" in str(e)

    def test_no_line_number(self):
        e = FdsParseError("oops")
        assert "line" not in str(e)


class TestFdsPluginError:
    def test_plugin_name_stored(self):
        e = FdsPluginError("load failed", plugin_name="my_plugin")
        assert e.plugin_name == "my_plugin"


class TestFdsConfigError:
    def test_key_stored(self):
        e = FdsConfigError("bad value", key="fds_binary")
        assert e.key == "fds_binary"


class TestFdsJobError:
    def test_job_id_stored(self):
        e = FdsJobError("timeout", job_id="job-001")
        assert e.job_id == "job-001"


class TestFdsNotFoundError:
    def test_name_stored(self):
        e = FdsNotFoundError("not found", name="mesh_01")
        assert e.name == "mesh_01"


class TestFdsTimeoutError:
    def test_timeout_seconds_stored(self):
        e = FdsTimeoutError("timed out", timeout_seconds=3600.0)
        assert e.timeout_seconds == 3600.0


class TestFdsBinaryError:
    def test_filepath_and_offset_stored(self):
        e = FdsBinaryError("bad record", filepath="test.sf", offset=128)
        assert e.filepath == "test.sf"
        assert e.offset == 128

    def test_is_fds_error(self):
        assert isinstance(FdsBinaryError("x"), FdsError)


class TestExceptionHierarchy:
    def test_all_subclass_fds_error(self):
        subclasses = [
            FdsValidationError, FdsExecutionError, FdsParseError,
            FdsSerializationError, FdsPluginError, FdsConfigError,
            FdsJobError, FdsNotFoundError, FdsTimeoutError, FdsBinaryError,
        ]
        for cls in subclasses:
            assert issubclass(cls, FdsError), f"{cls.__name__} not a subclass of FdsError"

    def test_catch_with_base_class(self):
        """All pyfds exceptions can be caught as FdsError."""
        for exc in [FdsValidationError("v"), FdsExecutionError("e"), FdsBinaryError("b")]:
            with pytest.raises(FdsError):
                raise exc
