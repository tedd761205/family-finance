# G-01-08 Production Migration Runbook

## Status

This runbook documents the guarded production migration workflow. It does not authorize or execute a production migration.

- Production baseline observed by the read-only preflight: `49ed3855c31c`.
- Repository Alembic head: `a7c9e1f3b5d7`.
- The six pending revisions have successfully upgraded a restored Neon snapshot from the production baseline.
- The production migration workflow is manual-only and requires a fresh backup, a successful restore test, a successful restored-snapshot rehearsal, a host allowlist, and an exact target confirmation.

## Required GitHub configuration

The existing repository secret `DATABASE_URL` must continue to point to the Neon **production** branch. Do not paste or print its value.

Add this repository variable:

- Name: `NEON_PRODUCTION_HOST`
- Value: the hostname only for the Neon production endpoint, copied from the Neon dashboard. Do not include a scheme, username, password, port, database name, or query parameters.

Location: GitHub repository → Settings → Secrets and variables → Actions → Variables → New repository variable.

The workflow refuses to continue if the configured hostname does not exactly match the host in `DATABASE_URL`.

## Evidence required at dispatch

Supply three successful GitHub Actions run IDs:

1. `Neon Database Backup` — completed successfully within the previous 24 hours, with its non-empty backup artifact still available.
2. `Neon Restore Test` — completed successfully after that backup, restoring into `g01-restore-test`.
3. `G-01-08 Restored Production Snapshot Migration Rehearsal` — completed successfully after the restore test, with its verification report still available.

The workflow verifies each run's repository, workflow path, branch, status, conclusion, chronology, and required artifact. It also compares the migration source files in the rehearsal commit with the current `main` branch. Documentation-only or workflow-only commits do not force a needless rehearsal; changes to migration sources, dependencies, Alembic configuration, or the role-catalog validator do.

Latest successful evidence at the time this runbook was written:

| Evidence | Run ID |
|---|---:|
| Neon Database Backup | `44294415773` |
| Neon Restore Test | `44294853198` |
| Restored-snapshot Migration Rehearsal | `44296697831` |

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
- Confirms the production endpoint matches `NEON_PRODUCTION_HOST` and database name is `neondb`.
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
