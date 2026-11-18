"""Regression guards for G-01-01 audit-log integration.

These tests ensure every current core create/update/void route stages an audit
record before committing its business transaction. The audit helper's behavior
and transaction semantics are covered in test_g01_01_security.py.
"""

import ast
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]

MUTATIONS = [
    ("app/routers/account.py", "create_account", "create"),
    ("app/routers/account.py", "update_account", "update"),
    ("app/routers/account.py", "deactivate_account", "void"),
    ("app/routers/category.py", "create_category", "create"),
    ("app/routers/category.py", "update_category", "update"),
    ("app/routers/category.py", "deactivate_category", "void"),
    ("app/routers/transaction.py", "create_transaction", "create"),
    ("app/routers/transaction.py", "update_transaction", "update"),
    ("app/routers/transaction.py", "void_transaction", "void"),
    ("app/routers/transfer.py", "create_transfer", "create"),
    ("app/routers/transfer.py", "update_transfer", "update"),
    ("app/routers/transfer.py", "void_transfer", "void"),
    ("app/routers/credit_card_payment.py", "create_credit_card_payment", "create"),
    ("app/routers/credit_card_payment.py", "update_credit_card_payment", "update"),
    ("app/routers/credit_card_payment.py", "void_credit_card_payment", "void"),
]


def _function_node(source: str, function_name: str) -> ast.FunctionDef:
    module = ast.parse(source)
    for node in module.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == function_name:
                return node
    raise AssertionError(f"Function not found: {function_name}")


@pytest.mark.parametrize(
    ("relative_path", "function_name", "expected_action"),
    MUTATIONS,
)
def test_core_mutation_stages_audit_before_commit(
    relative_path: str,
    function_name: str,
    expected_action: str,
):
    source = (ROOT / relative_path).read_text(encoding="utf-8")
    function = _function_node(source, function_name)

    audit_calls = []
    commit_calls = []

    for node in ast.walk(function):
        if not isinstance(node, ast.Call):
            continue

        if isinstance(node.func, ast.Name) and node.func.id == "add_audit_log":
            audit_calls.append(node)

        if (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "db"
            and node.func.attr == "commit"
        ):
            commit_calls.append(node)

    assert len(audit_calls) == 1, (
        f"{relative_path}:{function_name} must stage exactly one audit record"
    )
    assert commit_calls, f"{relative_path}:{function_name} must commit its mutation"
    assert audit_calls[0].lineno < min(call.lineno for call in commit_calls), (
        f"{relative_path}:{function_name} must stage the audit record before commit"
    )

    action_values = [
        keyword.value.value
        for keyword in audit_calls[0].keywords
        if keyword.arg == "action"
        and isinstance(keyword.value, ast.Constant)
    ]
    assert action_values == [expected_action]
