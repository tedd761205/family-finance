# G-01-08 Migration History Audit

Audit date: 2026-11-18  
Repository: `tedd761205/family-finance`  
Production revision observed by the read-only preflight: `49ed3855c31c`  
Repository head: `a7c9e1f3b5d7`

## Executive result

- The repository currently has one linear Alembic history from the initial family schema through G-01-07.
- Production is recorded at `49ed3855c31c`, which is an ancestor of the repository head.
- Six revisions are pending in production: `b1a7c903e642`, `c2d4e6f8a0b1`, `d5e7f9a1b3c5`, `e7f9a1b3c5d7`, `f1a2b3c4d5e6`, and `a7c9e1f3b5d7`.
- The read-only preflight and disposable PostgreSQL 18 migration simulation passed. This does not replace an upgrade rehearsal against a restored production snapshot.
- No production migration was executed as part of this audit.

## Revision chain

The checked-in revision dependencies form this single sequence:

1. `c6b970fa5b85` — initial family, users, roles, permissions and audit tables.
2. `5ea35371afe0` — role data scopes.
3. `9968d0341ee8` — revoked JWT tokens.
4. `0a3c7cfbf79a` — password reset tokens.
5. `e27056799259` — user token version.
6. `9c3acbe23257` — external login identities and nullable password hashes.
7. `b7c3fe056257` — accounts.
8. `66b1e3d6c67a` — categories, transfers and transactions.
9. `18c51cf1ba49` — unique active opening-balance index.
10. `49ed3855c31c` — credit-card payments and transaction linkage.
11. `b1a7c903e642` — bills.
12. `c2d4e6f8a0b1` — recurring bills.
13. `d5e7f9a1b3c5` — bill payments and refunds.
14. `e7f9a1b3c5d7` — private attachments.
15. `f1a2b3c4d5e6` — OCR tasks.
16. `a7c9e1f3b5d7` — notifications and export workflows.

Production is currently at item 10. Items 11–16 are the six pending revisions.

## Findings and operational cautions

### 1. Misleading historical filenames

Several migration files have the filename `*_add_password_reset_tokens_table.py`, although their revision docstrings and actual operations describe unrelated changes:

- `18c51cf1ba49`: opening-balance uniqueness.
- `49ed3855c31c`: credit-card payments.
- `66b1e3d6c67a`: categories, transfers and transactions.
- `b7c3fe056257`: accounts.
- `9c3acbe23257`: external login identities.
- `e27056799259`: token version.
- `0a3c7cfbf79a`: password reset tokens.

The revision IDs and `down_revision` values, rather than filenames, define Alembic identity and ordering. The audited graph is linear; the misleading filenames are a maintainability risk, not evidence of duplicate revision IDs. Avoid renaming already-deployed migration files during a production rollout unless a separate compatibility review is completed.

### 2. External identity downgrade requires special care

Revision `9c3acbe23257` makes `users.password_hash` nullable so a Google-only account can exist. Its downgrade attempts to make that column non-null before dropping `user_identities`.

If any user has a NULL password hash, PostgreSQL will reject the downgrade. Because PostgreSQL DDL is transactional under the normal Alembic transaction, the failed downgrade should roll back rather than silently dropping the identity table. This is a safe failure, but it means this revision is not automatically reversible while passwordless external-login accounts exist. Do not use a blanket downgrade as a production rollback strategy.

### 3. Migration rehearsal must start from the restored baseline

The new manual workflow `.github/workflows/g01-08-restored-db-migration-rehearsal.yml` is intended to upgrade the isolated `g01-restore-test` Neon branch from revision `49ed3855c31c` to the repository head. It checks the configured host and explicit target confirmation, verifies the restored baseline, preserves selected existing row counts, and checks the new tables, key indexes, category-scope triggers and role catalog.

The workflow changes only the configured restore-test branch. It does not target Render or production. Re-run the restore workflow first if the test branch no longer contains the known-good restored baseline.

## Production deployment gate

Do not run `alembic upgrade head` against production until all of the following are true:

1. A fresh production backup has completed and its artifact is readable.
2. Restore verification has succeeded on `g01-restore-test`.
3. The restored-snapshot migration rehearsal has succeeded from `49ed3855c31c` to `a7c9e1f3b5d7`.
4. The migration report and any warnings have been reviewed.
5. A separate, explicit authorization has been given for the production migration.

The current audit does not authorize or execute a production migration.
