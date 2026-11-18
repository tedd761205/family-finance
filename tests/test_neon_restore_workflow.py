from pathlib import Path


def test_neon_restore_workflow_exports_actual_host_for_python_guard():
    workflow = Path(".github/workflows/neon-restore-test.yml").read_text(
        encoding="utf-8"
    )
    validation_step = workflow.split(
        "- name: Validate test database connection and branch endpoint", 1
    )[1].split("- name: Restore dump into test branch", 1)[0]

    assert 'ACTUAL_HOST="$(python3 -c' in validation_step
    assert "export ACTUAL_HOST" in validation_step
    assert validation_step.index("export ACTUAL_HOST") < validation_step.index(
        "python3 - <<'PY'"
    )
    assert 'actual_host = os.environ["ACTUAL_HOST"].strip().lower()' in validation_step
    assert "if actual_host not in allowed_hosts:" in validation_step
