# G-01-08 Production Migration Runbook

## Status

This runbook documents the guarded production migration workflow. It does not authorize or execute a production migration.

- Production baseline for this migration: `f2a4c6e8b0d2` (family invitations already deployed).
- Repository Alembic target: `a8c4e2f6b1d3` (cross-currency bill payment fields plus structured purchase line items).
- The full migration chain from `f2a4c6e8b0d2` through `f5b7d9e1a3c5` to `a8c4e2f6b1d3` must be rehearsed on a fresh restored snapshot before production execution. The final revision adds only the `purchase_line_items` table and its constraints/index.
- The production migration workflow is manual-only and requires a fresh backup, a successful restore test, a successful restored-snapshot rehearsal, a host allowlist, and an exact target confirmation.

## Required GitHub configuration

The existing repository secret `DATABASE_URL` must continue to point to the Neon **production** branch. Do not paste or print its value.

Add these repository variables:

- `NEON_PRODUCTION_HOST`: hostname only for the Neon production endpoint.
- `NEON_RESTORE_TEST_HOST`: hostname only for the `g01-restore-test` endpoint.
- `NEON_RESTORE_TEST_BRANCH_ID`: exact Neon branch ID for `g01-restore-test` (starts with `br-`).

Add this repository secret:

- `NEON_API_KEY`: a Neon API key with read access to the project and branch metadata. Do not paste it into chat or workflow files.

The project and production branch are pinned in the workflow to project `wild-credit-40100572` and production branch `br-jolly-breeze-b3mereg2`. Before connecting to PostgreSQL, the workflows call the Neon API and verify project ID, branch ID, and exact branch name (`production` or `g01-restore-test`). They also retrieve that branch's compute endpoints, require exactly one active read-write endpoint, and require the database URL hostname to match the API-reported endpoint host (direct or its documented pooler hostname form) as well as the configured hostname. The restore provenance records the verified project, branch, and endpoint identity; the production gate checks those fields before accepting the restore evidence.

Location: GitHub repository → Settings → Secrets and variables → Actions. Add secrets under **Secrets** and values under **Variables**.

## Evidence required at dispatch

Supply three successful GitHub Actions run IDs:

1. `Neon Database Backup` — completed successfully within the previous 24 hours, with its non-empty backup artifact still available.
2. `Neon Restore Test` — completed successfully after that backup, restoring into `g01-restore-test`.
3. `G-01-08 Restored Production Snapshot Migration Rehearsal` — completed successfully after the restore test, with its verification report still available.

The workflow verifies each run's repository, workflow path, branch, status, conclusion, chronology, and required artifacts. The restore workflow also records a provenance artifact containing the exact backup run ID and the `g01-restore-test` confirmation; the production gate downloads it and requires it to match the selected backup run. It also compares migration source files in the rehearsal commit with current `main`. Documentation-only or workflow-only commits do not force a needless rehearsal; changes to migration sources, dependencies, Alembic configuration, or the role-catalog validator do.

The restore provenance artifact is required for the production gate. Use a fresh backup, restore it to `g01-restore-test`, then rehearse from the restored `f2a4c6e8b0d2` baseline through `f5b7d9e1a3c5` to `a8c4e2f6b1d3`. The restore test resets the isolated branch, so the rehearsal must run after it.

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

Before running `alembic upgrade a8c4e2f6b1d3`, the workflow:

- Confirms the exact target phrase.
- Verifies successful backup, restore-test, and rehearsal runs and the available backup/rehearsal artifacts.
- Confirms the rehearsal's migration sources match the current `main`.
- Confirms the Neon API reports the pinned project ID and production branch ID/name, then independently matches the production endpoint hostname and database name `neondb`.
- Opens a read-only transaction and requires the exact production baseline revision `f2a4c6e8b0d2`.
- Requires the exact 35-table baseline at `f2a4c6e8b0d2`, refuses if any of the four cross-currency bill-payment columns already exist, and refuses unexpected public tables.
- Captures selected existing row counts before migration.

After migration, it verifies Alembic revision `a8c4e2f6b1d3`, all existing finance tables, the four cross-currency bill-payment columns, the new `purchase_line_items` table, its family-safe transaction foreign key and creator foreign key, its nonblank-name/positive-quantity/nonnegative-price checks, its family/transaction index and family/id unique constraint, existing required indexes, bill-payment checks, category-scope triggers, unchanged selected existing row counts, and the role catalog. It uploads a report artifact.

## Failure and rollback policy

- Never use a blanket Alembic downgrade as the production rollback plan.
- In particular, the historical external-identity migration cannot be downgraded safely if Google-only users with NULL password hashes exist.
- If a migration step fails, do not blindly rerun the workflow. Inspect the run log and current Alembic revision first; earlier revisions may already have committed.
- Recovery must use the verified backup/Neon recovery procedure and a separately reviewed restore target. Do not restore over production without a separate explicit authorization.
- A successful schema migration does not by itself prove the Render application deployment, scheduled export worker, or end-to-end user flows are ready. Those remain separate rollout checks.

## Scope

This workflow is the only supported production migration entry point after this hardening change is merged. It does not change Render configuration, enable scheduled workers, or run automatically on deployment.
