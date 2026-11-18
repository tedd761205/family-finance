# G-01-08 Production Migration Runbook

## Status

This runbook documents the guarded production migration workflow. It does not authorize or execute a production migration.

- Production baseline observed by the read-only preflight: `49ed3855c31c`.
- Repository Alembic head: `a7c9e1f3b5d7`.
- The six pending revisions have successfully upgraded a restored Neon snapshot from the production baseline.
- The production migration workflow is manual-only and requires a fresh backup, a successful restore test, a successful restored-snapshot rehearsal, a host allowlist, and an exact target confirmation.

## Required GitHub configuration

The existing repository secret `DATABASE_URL` must continue to point to the Neon **production** branch. Do not paste or print its value.

Add these repository variables:

- `NEON_PRODUCTION_HOST`: hostname only for the Neon production endpoint.
- `NEON_RESTORE_TEST_HOST`: hostname only for the `g01-restore-test` endpoint.
- `NEON_RESTORE_TEST_BRANCH_ID`: exact Neon branch ID for `g01-restore-test` (starts with `br-`).

Add this repository secret:

- `NEON_API_KEY`: a Neon API key with read access to the project and branch metadata. Do not paste it into chat or workflow files.

The project and production branch are pinned in the workflow to project `wild-credit-40100572` and production branch `br-jolly-breeze-b3mereg2`. Before connecting to PostgreSQL, the workflows call the Neon API and verify project ID, branch ID, and exact branch name (`production` or `g01-restore-test`). The PostgreSQL hostname is then independently compared with the configured hostname.

Location: GitHub repository → Settings → Secrets and variables → Actions. Add secrets under **Secrets** and values under **Variables**.

## Evidence required at dispatch

Supply three successful GitHub Actions run IDs:

1. `Neon Database Backup` — completed successfully within the previous 24 hours, with its non-empty backup artifact still available.
2. `Neon Restore Test` — completed successfully after that backup, restoring into `g01-restore-test`.
3. `G-01-08 Restored Production Snapshot Migration Rehearsal` — completed successfully after the restore test, with its verification report still available.

The workflow verifies each run's repository, workflow path, branch, status, conclusion, chronology, and required artifacts. The restore workflow also records a provenance artifact containing the exact backup run ID and the `g01-restore-test` confirmation; the production gate downloads it and requires it to match the selected backup run. It also compares migration source files in the rehearsal commit with current `main`. Documentation-only or workflow-only commits do not force a needless rehearsal; changes to migration sources, dependencies, Alembic configuration, or the role-catalog validator do.

The restore provenance artifact was added by this hardening change. Therefore, the previously successful restore run `44294853198` predates that artifact and cannot be used for a future production migration dispatch. After this PR is merged, run a fresh backup if the existing backup is older than 24 hours, then run Neon Restore Test and the restored-snapshot Migration Rehearsal again. The new restore test resets the isolated branch to the baseline, so the rehearsal must run after it.

Latest successful evidence at the time this runbook was written:

| Evidence | Run ID |
|---|---:|
| Neon Database Backup | `44294415773` |
| Neon Restore Test | `44294853198` (pre-provenance; historical evidence only) |
| Restored-snapshot Migration Rehearsal | `44296697831` (historical evidence; rerun after the fresh restore) |

The backup evidence expires as a production gate after 24 hours. Generate a fresh backup and repeat restore/rehearsal if the evidence is no longer current or the restore branch has changed.

## Manual execution procedure

Do not start this workflow until a separate, explicit production-migration authorization has been given.

1. Open GitHub Actions → **Apply Alembic Migration**.
2. Select branch `main`.
3. Enter the three evidence run IDs.
4. Enter exactly `family-finance-production` in `target_confirmation`.
5. Start the workflow only after reviewing the target and evidence IDs.

Before running `alembic upgrade head`, the workflow:

- Confirms the exact target phrase.
- Verifies successful backup, restore-test, and rehearsal runs and the available backup/rehearsal artifacts.
- Confirms the rehearsal's migration sources match the current `main`.
- Confirms the Neon API reports the pinned project ID and production branch ID/name, then independently matches the production endpoint hostname and database name `neondb`.
- Opens a read-only transaction and requires the exact production baseline revision `49ed3855c31c`.
- Requires the audited 18-table baseline and refuses if any of the ten new G-01 tables already exist or unexpected public tables are present.
- Captures selected existing row counts before migration.

After migration, it verifies the repository Alembic head, all ten new tables, six required indexes, two category-scope triggers, unchanged selected existing row counts, and the role catalog. It uploads a report artifact.

## Failure and rollback policy

- Never use a blanket Alembic downgrade as the production rollback plan.
- In particular, the historical external-identity migration cannot be downgraded safely if Google-only users with NULL password hashes exist.
- If a migration step fails, do not blindly rerun the workflow. Inspect the run log and current Alembic revision first; earlier revisions may already have committed.
- Recovery must use the verified backup/Neon recovery procedure and a separately reviewed restore target. Do not restore over production without a separate explicit authorization.
- A successful schema migration does not by itself prove the Render application deployment, scheduled export worker, or end-to-end user flows are ready. Those remain separate rollout checks.

## Scope

This workflow is the only supported production migration entry point after this hardening change is merged. It does not change Render configuration, enable scheduled workers, or run automatically on deployment.
