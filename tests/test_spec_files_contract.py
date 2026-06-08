"""Unit tests for spec Files contract parsing and target_files comparison."""

from core.specs.files_contract import (
    FilesContract,
    build_contract_warnings,
    contract_paths_missing_from_target,
    parse_files_contract,
)

EDIT_READ_SECTION = """\
Repo-relative paths for implement.

### Edit

- `expense_splitter/cli.py`

### Read (include in target_files)

- `expense_splitter/splitter.py` — public API from step 1
"""

LEGACY_FLAT_SECTION = """\
- `scraped_content.txt`
- other.py
"""

EDIT_ONLY_SECTION = """\
### Edit

- `pkg/module.py`
"""


def test_parse_edit_and_read_subsections():
    contract = parse_files_contract(EDIT_READ_SECTION)
    assert contract.edit == ["expense_splitter/cli.py"]
    assert contract.read == ["expense_splitter/splitter.py"]
    assert contract.all_paths == [
        "expense_splitter/cli.py",
        "expense_splitter/splitter.py",
    ]


def test_parse_legacy_flat_bullets():
    contract = parse_files_contract(LEGACY_FLAT_SECTION)
    assert contract.edit == ["other.py", "scraped_content.txt"]
    assert contract.read == []
    assert contract.all_paths == ["other.py", "scraped_content.txt"]


def test_parse_edit_only():
    contract = parse_files_contract(EDIT_ONLY_SECTION)
    assert contract.edit == ["pkg/module.py"]
    assert contract.read == []
    assert contract.all_paths == ["pkg/module.py"]


def test_parse_empty_section():
    contract = parse_files_contract("")
    assert contract == FilesContract(edit=[], read=[], all_paths=[])


def test_contract_paths_missing_from_target():
    contract = parse_files_contract(EDIT_READ_SECTION)
    missing = contract_paths_missing_from_target(
        contract, ["expense_splitter/cli.py"]
    )
    assert missing == ["expense_splitter/splitter.py"]


def test_contract_paths_all_in_target_no_missing():
    contract = parse_files_contract(EDIT_READ_SECTION)
    missing = contract_paths_missing_from_target(
        contract,
        [
            "expense_splitter/cli.py",
            "expense_splitter/splitter.py",
        ],
    )
    assert missing == []


def test_contract_paths_normalizes_target_files():
    contract = parse_files_contract(EDIT_ONLY_SECTION)
    missing = contract_paths_missing_from_target(
        contract, ["./pkg/module.py"]
    )
    assert missing == []


READ_NONE_SECTION = """\
### Edit

- `expense_splitter/cli.py`

### Read

- `(none)`
"""

EDIT_NA_SECTION = """\
### Edit

- n/a
- `pkg/real.py`

### Read

- `(none)`
"""


def test_read_placeholder_none_ignored():
    contract = parse_files_contract(READ_NONE_SECTION)
    assert contract.read == []
    assert "(none)" not in contract.all_paths
    assert contract.edit == ["expense_splitter/cli.py"]


def test_edit_placeholder_na_ignored():
    contract = parse_files_contract(EDIT_NA_SECTION)
    assert contract.edit == ["pkg/real.py"]
    assert "n/a" not in contract.all_paths


def test_real_paths_with_none_in_name_not_filtered():
    section = """\
### Edit

- `none.py`
- `n/a/foo.py`
"""
    contract = parse_files_contract(section)
    assert contract.edit == ["n/a/foo.py", "none.py"]
    assert contract.all_paths == ["n/a/foo.py", "none.py"]


def test_placeholder_read_not_in_missing_from_target():
    contract = parse_files_contract(READ_NONE_SECTION)
    missing = contract_paths_missing_from_target(
        contract, ["expense_splitter/cli.py"]
    )
    assert "(none)" not in missing
    assert missing == []


def test_build_contract_warnings():
    warnings = build_contract_warnings(["a.py", "b.py"])
    assert warnings == [
        "Spec Files lists paths not in target_files: a.py, b.py"
    ]
    assert build_contract_warnings([]) == []
