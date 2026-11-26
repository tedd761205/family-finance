# G-01-08 Migration History Audit

Audit date: 2026-11-25  
Repository: `tedd761205/family-finance`  
Production baseline for the next guarded migration: `f2a4c6e8b0d2`  
Repository Alembic head: `f5b7d9e1a3c5`

## Executive result

- The checked-in Alembic graph is a single linear history.
- The family invitation revision `f2a4c6e8b0d2` is the production baseline used by the current guarded migration workflow.
- The cross-currency bill payment revision `f5b7d9e1a3c5` is the only revision pending for the next production rollout.
- The new revision adds account-side amount/currency, locked exchange rate, and refund exchange-difference fields to `bill_payments`; it does not create or delete tables.
- Existing payment rows are backfilled from their linked account and retain their historical amount and currency unchanged.
- No production migration is authorized or executed by this audit.

## Revision chain

The relevant tail of the single Alembic history is:

1. `f1a2b3c4d5e6` — durable OCR task workflow.
2. `a7c9e1f3b5d7` — notifications and export workflows.
3. `b8d1f4a6c9e2` — staged bank statement imports.
4. `d3e5f7a9b1c3` — reconciliation sessions and match allocations.
5. `f4a6c8d0e2b4` — reconciliation exclusion history.
6. `a6b8c0d2e4f6` — reconciliation issue classification and resolution.
7. `c7d9e1f3a5b7` — reconciliation issue update permission.
8. `f2a4c6e8b0d2` — family invitations.
9. `f5b7d9e1a3c5` — cross-currency bill payment amounts, account currency, exchange rates, and refund exchange differences.

The earlier revisions from the initial family schema through G-01-07 are documented in the original audit history and remain unchanged.

## Cross-currency bill payment migration

Revision `f5b7d9e1a3c5` adds four columns to `bill_payments`:

- `account_amount`: actual amount posted to the selected account.
- `account_currency_code`: currency of the selected account.
- `exchange_rate`: account-currency units per one bill-currency unit.
- `exchange_difference`: refund-only difference against the original payment's locked rate.

The migration backfills all existing records using the linked account's currency, copies the existing payment amount to `account_amount`, sets the exchange rate to 1, and sets the exchange difference to 0. This is correct for the previous same-currency-only payment workflow. The migration then makes the new account-side columns non-null and adds check constraints.

No automatic exchange-rate provider, paid service, or new database resource is introduced.

## Findings and operational cautions

### 1. Historical migration filenames

Several historical migration filenames are misleading and use names such as `*_add_password_reset_tokens_table.py` for unrelated changes. Revision IDs and `down_revision` values define Alembic identity and ordering. Do not rename already-deployed migration files during a production rollout.

### 2. External identity downgrade

Revision `9c3acbe23257` makes `users.password_hash` nullable so Google-only accounts can exist. Its downgrade attempts to make that column non-null before dropping `user_identities`. If any user has a NULL password hash, PostgreSQL will reject the downgrade. Do not use a blanket downgrade as the production rollback plan.

### 3. Migration rehearsal

The manual workflow `.github/workflows/g01-08-restored-db-migration-rehearsal.yml` must upgrade a fresh restored production snapshot from `f2a4c6e8b0d2` to `f5b7d9e1a3c5`. It verifies the exact isolated Neon host, baseline tables and revision, preserved row counts, new columns, check constraints, existing indexes, triggers, and role catalog.

The workflow changes only the configured `g01-restore-test` branch. It does not target Render or production.

## Production deployment gate

Do not execute the production migration until all of the following are true:

1. A fresh production backup has completed and its artifact is readable.
2. Restore verification has succeeded on `g01-restore-test` using the current production baseline.
3. The restored-snapshot migration rehearsal has succeeded from `f2a4c6e8b0d2` to `f5b7d9e1a3c5`.
4. The migration report and warnings have been reviewed.
5. A separate, explicit authorization has been given for the production migration.

The guarded production workflow verifies the exact baseline, Neon project/branch/endpoint identity, backup/restore/rehearsal evidence, selected row counts, and the exact migration target. This audit does not authorize or execute a production migration.
