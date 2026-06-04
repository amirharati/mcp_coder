import io
import sys

from core.config.aider_runtime import create_delegation_io
from core.engine.stdio_isolation import bind_aider_io_to_buffer, isolated_stdio


def test_isolated_stdio_captures_print():
    with isolated_stdio() as (out, err):
        print("hello-stdout")
        print("hello-stderr", file=sys.stderr)
    assert "hello-stdout" in out.getvalue()
    assert "hello-stderr" in err.getvalue()


def test_bind_aider_io_print_goes_to_buffer():
    pytest = __import__("pytest")
    pytest.importorskip("aider")
    buf = io.StringIO()
    io_obj, _ = create_delegation_io()
    bind_aider_io_to_buffer(io_obj, buf)
    io_obj.print("token line")
    io_obj.tool_output("tool line")
    text = buf.getvalue()
    assert "token line" in text
    assert "tool line" in text
