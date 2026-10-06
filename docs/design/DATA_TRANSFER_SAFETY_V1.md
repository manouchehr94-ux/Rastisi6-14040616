# Data transfer safety v1 («ورود اطلاعات» / «خروج اطلاعات»)

Branch `redesign/data-transfer-safety-v1`. Follow-up to `XLSX_IMPORT_EXPORT_V1.md`.
Internal names (`ImportJob`, `ExportJob`, `import-*`/`export-*` routes) are unchanged; only
merchant-facing wording moved to «ورود اطلاعات» (import) and «خروج اطلاعات» (export),
including the Settings tabs and the Ctrl+K palette («تنظیمات ← ورود اطلاعات»).

## Import is fail-closed

A file is executable only if **zero** rows are blocking. Blocking conditions
(`import_service.job_execution_blockers`, also re-evaluated at execution time):

* any row with a validation error (`invalid`/`failed`) — including formula cells,
  unknown references, create-only/update-only mismatches, duplicate SKUs, foreign-store ids;
* an empty file;
* a job-level plan limit: the file would create more new products than the plan allows;
* the job is not in `preview_ready` (cancelled, finished, processing…).

Warnings (e.g. an ignored extra column, a zero-delta inventory row) are **not** blocking. They
stay visible, in amber, clearly separate from the red errors, and the page says
«هشدارها مانعِ اجرا نیستند».

UI: the preview is always produced and lists every error (Excel row, merchant column, Persian
explanation, XLSX error report). With a blocking error the «تأیید اجرای واقعی» button and form
are not rendered; copy: «این فایل قابل اجرا نیست. ابتدا همه خطاها را اصلاح و فایل را دوباره بارگذاری کنید.»
Clean file: «فایل با موفقیت بررسی شد. همه ردیف‌ها معتبرند و آماده اجرا هستند.» plus a
confirmation that states Store data will change. A direct POST to `import-execute` gets the same
answer as the UI: nothing is applied.

## Execution (`import_service.run_execution`)

1. Only `uploaded`/`preview_ready` jobs run. A compare-and-set `UPDATE … WHERE status IN (…)`
   claims the job (`processing`), so finished jobs and concurrent double-submits cannot replay.
2. Feature gate (`enforce_import_allowed`) and monthly row budget (`check_import_row_budget`) are
   re-checked. Permission is enforced by the view decorator (`IMPORT_EXPORT_MANAGE`) and Store
   resolution.
3. **Revalidation**: the original source file is re-read and *every* row is validated again
   against the current Store (same validators as the preview, dry-run, no writes), plus the
   product-creation budget for the whole file. The stored preview is never trusted.
   If anything blocks: the fresh preview replaces the old one, the job returns to
   `preview_ready`, `ImportExecutionBlocked` is raised with an explanation («اطلاعاتِ فروشگاه از
   زمانِ پیش‌نمایش تغییر کرده …» when the old preview was clean), and the audit log records
   `import.execution_rejected`. No business data changed.
4. **Mutation**: one outer `transaction.atomic()` wraps *all* batches (the existing per-batch and
   per-row savepoints stay inside it) and the quota consumption (`consume_import_rows`).
   Rows are validated once more inside the transaction against a fresh cache. If any row ends
   `invalid`/`failed`, or any exception escapes, everything — products, variants, `StockMovement`,
   aggregate/warehouse stock, quota usage, audit entries written by services — is rolled back.
5. **Outside the transaction**, after a rollback: the job is saved as `failed` with
   «اجرا متوقف شد و هیچ تغییری روی فروشگاه اعمال نشد. ردیف N: <دلیل>», row results are rewritten
   (failing row `failed` with its message; every other row `valid` with the warning
   «این ردیف اعمال نشد؛ چون کلِ واردات بازگردانده شد»), the XLSX error report is generated and
   `import.execution_rolled_back` (result = failure) is audited. An unexpected exception is logged
   and shown to the merchant as a generic message. A failed job is final (no replay).
   If only an `invalid` row appears during mutation (concurrent change), the job returns to a fresh
   preview (`reason: concurrent`) instead of `failed`.
6. Success: `completed`, counts, `import.execution_completed`.

Audit codes: `import.execution_started`, `import.execution_rejected` (validation/limits, nothing
ran), `import.execution_rolled_back` (ran, failed, reverted), `import.execution_completed`.

`completed_with_errors` is no longer produced; the enum value stays so old jobs render
(«تکمیل‌شده با خطا (قدیمی)»). No migration is needed for statuses.

Known limits: reservation conflicts and slug/DB uniqueness races depend on row order and are
only detected while applying (not in the dry-run); they roll the whole file back and are reported
per row. `generate_variants` creates all combinations of a product at once, so within one file the
combinations it generates count as *new* for later rows of the same product (otherwise create-only
files with several variants would fail). Execution is synchronous like before; a hard process
crash mid-run leaves the database transaction rolled back by the DB, but the job stays in
`processing`.

## Direct-download «خروج اطلاعات»

`POST export-create` → `export_service.generate_export` builds the workbook in memory and the view
returns it as the response (`Content-Type` XLSX, `Content-Disposition: attachment;
filename="rastisi-<type>-<YYYY-MM-DD>.xlsx"`, `Cache-Control: no-cache, no-store …`). Nothing is
written to `private_storage`; there is no history table and no second «download» click. Customer
bulk «خروج انتخاب‌شده‌ها» uses the same path.

Kept: view permission (`IMPORT_EXPORT_VIEW`/`CUSTOMER_EXPORT` per type), Store scoping, feature gate and
monthly allowance (checked **before** building, consumed **only after** the workbook exists — a failed
build consumes nothing), audit (`export.completed` with `delivery: direct_download`, `retained:
false`, or `export.failed`), formula-safe cells and all XLSX formatting/guide sheet.

`ExportJob` is still written, as lightweight metadata only: type, filters, requesting user, row
count, status, timestamps. For new exports `file` is empty and `expires_at` is `NULL`; they can
never be downloaded later (`export-download` returns 404 without a file). No migration.

### Legacy retained exports

Jobs created before this change keep their file until their own `expires_at` (7 days). Until then
`export-download` still serves them with their real type (`.xlsx` or `.csv`), with the same permission
checks, and the page lists them under «فایل‌هایِ قدیمی». `cleanup_expired_exports` (unchanged) marks
them `expired` and deletes the files. No new export ever enters the retention workflow.

## Smaller changes

* `StockMovement.Reason.IMPORT_ADJUSTMENT` label now says «ورود اطلاعات» (label-only migration
  `catalog.0040`). Plan entitlement labels were renamed likewise.
* Template/guide/error-report copy no longer says healthy rows are applied while others fail.
