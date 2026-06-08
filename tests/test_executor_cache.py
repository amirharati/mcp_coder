from unittest.mock import MagicMock

from core.session.executor_cache import clear_executor_cache, drop_coder, get_or_create_coder


def test_executor_cache_reuses_same_target_files():
    clear_executor_cache()
    create_fn = MagicMock(side_effect=lambda: object())

    bundle1, reused1, recreated1 = get_or_create_coder("sess-1", ["a.py"], create_fn)
    bundle2, reused2, recreated2 = get_or_create_coder("sess-1", ["a.py"], create_fn)

    assert bundle1 is bundle2
    assert reused1 is False
    assert recreated1 is True
    assert reused2 is True
    assert recreated2 is False
    assert create_fn.call_count == 1


def test_executor_cache_recreates_on_target_files_change():
    clear_executor_cache()
    create_fn = MagicMock(side_effect=[object(), object()])

    _, _, recreated1 = get_or_create_coder("sess-2", ["a.py"], create_fn)
    _, reused2, recreated2 = get_or_create_coder("sess-2", ["b.py"], create_fn)

    assert recreated1 is True
    assert reused2 is False
    assert recreated2 is True
    assert create_fn.call_count == 2


def test_executor_cache_recreates_on_package_key_change():
    clear_executor_cache()
    create_fn = MagicMock(side_effect=[object(), object()])

    _, _, recreated1 = get_or_create_coder(
        "sess-pkg",
        ["a.py"],
        create_fn,
        context_package_key="hash-one",
    )
    _, reused2, recreated2 = get_or_create_coder(
        "sess-pkg",
        ["a.py"],
        create_fn,
        context_package_key="hash-two",
    )

    assert recreated1 is True
    assert reused2 is False
    assert recreated2 is True
    assert create_fn.call_count == 2


def test_executor_cache_reuses_same_package_key():
    clear_executor_cache()
    create_fn = MagicMock(side_effect=lambda: object())

    _, reused1, recreated1 = get_or_create_coder(
        "sess-pkg2",
        ["a.py"],
        create_fn,
        context_package_key="hash-same",
    )
    _, reused2, recreated2 = get_or_create_coder(
        "sess-pkg2",
        ["a.py"],
        create_fn,
        context_package_key="hash-same",
    )

    assert reused1 is False
    assert recreated1 is True
    assert reused2 is True
    assert recreated2 is False
    assert create_fn.call_count == 1


def test_executor_cache_legacy_reuse_without_package_key():
    clear_executor_cache()
    create_fn = MagicMock(side_effect=lambda: object())

    _, reused1, _ = get_or_create_coder("sess-legacy", ["a.py"], create_fn)
    _, reused2, recreated2 = get_or_create_coder("sess-legacy", ["a.py"], create_fn)

    assert reused1 is False
    assert reused2 is True
    assert recreated2 is False
    assert create_fn.call_count == 1


def test_drop_coder_clears_entry():
    clear_executor_cache()
    create_fn = MagicMock(side_effect=lambda: object())
    get_or_create_coder("sess-3", ["a.py"], create_fn)
    drop_coder("sess-3")
    _, reused, recreated = get_or_create_coder("sess-3", ["a.py"], create_fn)
    assert reused is False
    assert recreated is True
    assert create_fn.call_count == 2
