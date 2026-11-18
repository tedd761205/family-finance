from pathlib import Path


def test_neon_restore_workflow_exports_actual_host_for_python_guard():
    workflow = Path(".github/workflows/neon-restore-test.yml").read_text(
        encoding="utf-8"
    )
    validation_step = workflow.split(
        "- name: Validate test database connection and branch endpoint", 1
    )[1].split("- name: Reset public schema on verified test branch", 1)[0]

    assert 'ACTUAL_HOST="$(python3 -c' in validation_step
    assert "export ACTUAL_HOST" in validation_step
    assert validation_step.index("export ACTUAL_HOST") < validation_step.index(
        "python3 - <<'PY'"
    )
    assert 'actual_host = os.environ["ACTUAL_HOST"].strip().lower()' in validation_step
    assert "if actual_host not in allowed_hosts:" in validation_step


def test_neon_restore_resets_schema_only_after_branch_identity_guard():
    workflow = Path(".github/workflows/neon-restore-test.yml").read_text(
        encoding="utf-8"
    )
    guard = workflow.index(
        "- name: Validate test database connection and branch endpoint"
    )
    reset = workflow.index("- name: Reset public schema on verified test branch")
    restore = workflow.index("- name: Restore dump into test branch")

    assert guard < reset < restore
    reset_step = workflow[reset:restore]
    assert "DROP SCHEMA public CASCADE" in reset_step
    assert "CREATE SCHEMA public AUTHORIZATION CURRENT_USER" in reset_step
    assert "GRANT USAGE ON SCHEMA public TO PUBLIC" in reset_step


def test_neon_restore_does_not_use_pg_restore_clean_after_schema_reset():
    workflow = Path(".github/workflows/neon-restore-test.yml").read_text(
        encoding="utf-8"
    )
    restore_step = workflow.split(
        "- name: Restore dump into test branch", 1
    )[1].split("- name: Verify restored schema and data", 1)[0]

    assert "pg_restore" in restore_step
    assert "--no-owner --no-acl --exit-on-error" in restore_step
    assert "--clean" not in restore_step
    assert "--if-exists" not in restore_step
