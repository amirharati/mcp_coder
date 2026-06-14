"""Verify that contextvars propagate into ThreadPoolExecutor workers via copy_context."""
import concurrent.futures
import contextvars

_test_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("test_var", default=None)


def test_contextvar_visible_with_copy_context():
    """copy_context().run() makes the calling context available in the worker thread."""
    _test_var.set("hello")
    ctx = contextvars.copy_context()

    def _read():
        return _test_var.get()

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        val = pool.submit(ctx.run, _read).result()

    assert val == "hello"


def test_contextvar_not_visible_without_copy_context():
    """Without copy_context, the worker thread sees None (documents the bug)."""
    _test_var.set("hello")

    def _read():
        return _test_var.get()

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        val = pool.submit(_read).result()

    assert val is None  # default — demonstrates original bug
