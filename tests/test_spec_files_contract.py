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


def test_build_contract_warnings():
    warnings = build_contract_warnings(["a.py", "b.py"])
    assert warnings == [
        "Spec Files lists paths not in target_files: a.py, b.py"
    ]
    assert build_contract_warnings([]) == []
