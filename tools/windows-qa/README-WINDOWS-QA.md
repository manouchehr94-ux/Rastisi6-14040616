# RastiSi — Windows QA guide (Notifications / SMS / Email)

You do **not** edit any file and you do **not** resolve any Git conflict. Everything runs in a **separate Git worktree with its own
database** under `%LOCALAPPDATA%\RastiSiQA\`. Your normal checkout, your branches, Claude's and Kiro's worktrees are never touched.
No AWS credentials are needed, no real e-mail leaves your computer (the *fake* provider writes each message into a local folder),
and no DNS record is read or written.

> **What this QA can and cannot prove.** It proves the *product behaviour* (screens, rules, templates, sender policy, history, suppression,
> isolation, SMS/checkout unchanged). It does **not** prove real deliverability: nothing here talks to Amazon SES, DNS, or a real inbox.
> Those are the separate, explicitly-confirmed **live checks** at the end of this guide.

## 0. One-time requirements
| need | how to check | if missing |
|---|---|---|
| Windows 10/11, **PowerShell 5.1** (built in) or PowerShell 7 | `$PSVersionTable.PSVersion` | — |
| **Git for Windows** | `git --version` | https://git-scm.com/download/win |
| **Python 3.10+** (3.11 recommended), "py" launcher or on PATH | `py -3 --version` | https://www.python.org/downloads/ (tick *Add python.exe to PATH*) |
| Internet for the first `pip install` (≈ 3–5 min, one time) | | corporate proxy: set `HTTPS_PROXY` first |
| A modern browser (Edge / Chrome / Firefox resolve `*.localhost` automatically) | | otherwise see "hosts file" below |

## 1. Start (copy-paste, PowerShell, from your RastiSi clone folder)
```powershell
cd C:\path\to\Rastisi6-14040616
git fetch origin kiro/notifications-email-engine-20261104
git worktree add --detach "$env:LOCALAPPDATA\RastiSiQA\launcher" origin/kiro/notifications-email-engine-20261104
powershell -ExecutionPolicy Bypass -File "$env:LOCALAPPDATA\RastiSiQA\launcher\tools\windows-qa\Start-RastiSiQA.ps1" -RepoPath (Get-Location).Path -OpenBrowser
```
(The 2nd line only *adds* a folder; it does not change the branch you are on. If you already have the branch checked out, you can run
`.\tools\windows-qa\Start-RastiSiQA.ps1` directly.)

The script prints 9 numbered steps, then exactly this kind of block (your port may differ — it picks the first free port from 8765):
```
  Platform admin : http://platformadmins.rastisi.localhost:8765/
      login      : qa-platform@rastisi.test   password: Qa-xxxxxxxxx-1
  Central login  : http://rastisi.localhost:8765/login/
  Store admin    : http://qa-a.rastisi.localhost:8765/admin-portal/      store qa-no-domain  login: 09121110001   sender: inactive
  Store admin    : http://qa-b.rastisi.localhost:8765/admin-portal/      store qa-pending    login: 09121110002   sender: pending info@pendingstore.test
  Store admin    : http://qa-bike.rastisi.localhost:8765/admin-portal/   store qa-bike       login: 09121110003   sender: active  info@mybikestore.test
  Store admin    : http://qa-other.rastisi.localhost:8765/admin-portal/  store qa-other      login: 09121110004   sender: active  info@otherstore.test
  Fake mailbox   : C:\Users\you\AppData\Local\RastiSiQA\runs\<time>\mailbox
```
All QA accounts share one throw-away password (shown at the end, also in `QA-INFO.md` of the run folder). Store owners sign in on the
**central login** page; opening a store-admin URL redirects you there and brings you back automatically.

What the script did for you (and refuses to continue if any step fails, with a plain message): found Python → created a **detached worktree** of the
branch → created/reused a QA-only virtualenv (outside every worktree) and verified Django/boto3/dnspython/Pillow/… are importable →
**proved the database file is inside the run folder** → `manage.py check` → `makemigrations --check` → `migrate` → seeded 4 stores → started the
server (127.0.0.1 only) and a background worker (sends queued e-mail every 5 s) → waited until HTTP answers.

**hosts file (only if `*.localhost` does not open).** Add this line with Notepad *run as Administrator* to `C:\Windows\System32\drivers\etc\hosts`:
`127.0.0.1 rastisi.localhost platformadmins.rastisi.localhost qa-a.rastisi.localhost qa-b.rastisi.localhost qa-bike.rastisi.localhost qa-other.rastisi.localhost`

## 2. Run the automatic checks first (2 minutes)
```powershell
powershell -ExecutionPolicy Bypass -File "$env:LOCALAPPDATA\RastiSiQA\launcher\tools\windows-qa\Invoke-RastiSiAcceptanceCheck.ps1"
```
Real HTTP, real cookies, real host routing, real worker, fake mail. Expected last lines: `SUMMARY: 55 passed, 0 failed, 3 manual-only`
and a table in `ACCEPTANCE-REPORT.md` (run folder). It covers everything in scenarios A–L and N that a computer can judge. The three
**MANUAL** rows (storefront click-through, visual RTL, time-based expiry) are for you, below. *The acceptance script changes the demo data
(sends mails, edits templates, verifies `pendingstore.test`); for a clean manual pass start a new run.*

## 3. Manual acceptance scenarios (do these in the browser)
Helper for the "provider" side (use `-Action ...`, always the newest run):
`.\Invoke-RastiSiQATool.ps1 -Action Status | VerifyDomain -Domain pendingstore.test | FailDomain -Domain ... | RunWorkers | PlaceOrder | Event -EventType bounce | ShowMailbox | OpenMailbox`

| # | Scenario | Do | Expected |
|---|---|---|---|
| **A** | Platform admin edits a **default e-mail template** | Platform admin → *اعلان‌ها* → open `order.created` → change e-mail subject to `A-default {order_number}` → save | Saved; *preview* works; revision recorded (audit page). `PlaceOrder` + wait 5 s → `ShowMailbox` shows a message whose subject starts `A-default` for stores **without** an override. |
| **B** | A **store overrides** the e-mail | Store `qa-bike` → *اعلان‌ها* → `order.created` → e-mail tab → own subject/body (HTML optional) → save | Next order mail from `qa-bike` uses the store text; platform default unchanged; `qa-other` unaffected. |
| **C** | Store edits **SMS** | Same page → SMS tab → change text, save | Text persisted per store; platform SMS default unchanged. (SMS goes through the existing SMS stack; with the demo "console" SMS backend nothing is actually texted.) |
| **D** | **Independent channel toggles** | Store → *کانال‌ها* → switch **e-mail off** for `order.created`, SMS stays | Next order: no e-mail, SMS behaviour unchanged; security templates cannot be switched off. |
| **E** | **No verified domain** | Store `qa-no-domain` → *فرستنده* | Status **غیرفعال**; Persian reason ("فروشگاه هنوز دامنه‌ی اختصاصی ندارد"), corrective step, *who acts* (مالکِ دامنه), last-check time, retry button. **No** RastiSi address offered. Only e-mail is blocked — the store still works. |
| **F** | **Pending DNS** | Store `qa-pending` → *فرستنده* | Status **در انتظار تأیید**; the exact 3 CNAME records (name, relative name, value); *website verification* and *e-mail verification* shown as two separate things; advisory SPF/DMARC box (never blocking); automatic-DNS note explaining why it is manual. |
| **G** | **Verified sender sends** | `Invoke-RastiSiQATool.ps1 -Action VerifyDomain -Domain pendingstore.test`, then press **بررسیِ دوباره** | Status becomes **فعال**, address `info@pendingstore.test`. (Only the *provider* verdict activates it.) In platform admin → *اعلان‌ها* → a template → *test send* with that store → mail appears in the mailbox. |
| **H** | **Received mail shows the store domain** | `Invoke-RastiSiQATool.ps1 -Action OpenMailbox`, open the `.html` | `From: info@mybikestore.test` (store name as display name) — never a RastiSi address. Header/footer use store name. |
| **I** | **History** | Store → *تاریخچه* | Row per message: status, provider name, **provider message id**, delivery column (— → *برگشت خورد* after a bounce). |
| **J** | **Bounce / complaint → suppression** | `-Action Event -EventType bounce` (twice with the same `-EventId x` to see idempotency), then place another order | Recipient suppressed for **that store only**; next mail to them is not sent; complaint is recorded; duplicate event ignored. |
| **K** | **Tenant isolation** | Sign in as `qa-other` (09121110004) | Sees only its own override marker `QA-OVERRIDE-TENANT-D`, own domain, own history. Platform pages are 404/403 on a store host. Limited platform member `qa-catalog-only@rastisi.test` can view the catalog but gets **403** on senders/delivery/editing. |
| **L** | **SMS + checkout unchanged** | `-Action PlaceOrder` (or buy a product on the demo storefront) | COD order total exactly 5,000,000, payment status pending, no change to financial screens; SMS settings page still works. |
| **M** | **RTL desktop + mobile** | Open the sender, channels and template pages at ~1280 px and with the browser in 390 px device mode | Right-to-left layout, no horizontal scroll except inside the DNS table, buttons reachable. Reference screenshots: `docs/notifications/ui-evidence/`. |
| **N** | **Repeated / expired events** | `-Action Event -EventType delivery -EventId same` ×2 | One stored event, no duplicate. Expired/stale mails are never sent late — covered by `apps.notifications.tests.test_expiry` (34 tests); time-travel is not reproduced here. |

Run history of e-mails any time: `Invoke-RastiSiQATool.ps1 -Action ShowMailbox` (From / To / Subject / path of the `.html`).

## 4. Finish / clean up
```powershell
.\Stop-RastiSiQA.ps1                       # stop server + worker, keep data
.\Remove-RastiSiQA.ps1 -KeepArtifacts      # delete the worktree/DB/run folder, but copy logs + mailbox + QA-INFO to %LOCALAPPDATA%\RastiSiQA\artifacts\<run>
.\Remove-RastiSiQA.ps1 -All -IncludeVenvs  # remove every QA run and the shared virtualenv
git worktree remove --force "$env:LOCALAPPDATA\RastiSiQA\launcher"   # remove the launcher worktree from step 1
```
`Remove-*` refuses to delete anything outside `%LOCALAPPDATA%\RastiSiQA` or without the `.rastisi-qa` marker file.

## 5. Troubleshooting
| symptom | fix |
|---|---|
| `No usable Python 3.10+ found` | install Python; or pass `-PythonPath C:\Path\python.exe` (a wrong explicit path is an error, never silently ignored) |
| Microsoft Store opens when `python` is typed | disable *App execution aliases* for python in Windows settings, or use `py -3`/`-PythonPath` |
| `*.rastisi.localhost` "site can't be reached" | add the hosts line above |
| port busy | automatic (next free port); URLs printed at the end are always correct |
| `pip install` fails | see `logs\pip-install.log` in the run folder; behind a proxy set `HTTPS_PROXY` |
| need the server logs | `logs\server.err.log`, `logs\worker.out.log` (UTF-8) in the run folder |
| Execution policy blocks scripts | use `powershell -ExecutionPolicy Bypass -File ...` exactly as shown (process-only, no system change) |

## 6. LIVE checks (separate from everything above — need real AWS / DNS / public HTTPS)
Nothing in sections 1–4 does these. They are **blocked until the product owner provides** an AWS account/region, a real domain with DNS access, and a public HTTPS host.
Follow `docs/notifications/AWS_ACTIVATION_RUNBOOK.md`. The only script that can send real mail:
```powershell
# read-only: is the sender domain verified for sending in SES? (sends nothing; fails loudly if not)
.\Invoke-RastiSiLiveSesSmoke.ps1 -FromAddress info@yourdomain.com -Region eu-west-1
# sends ONE message to Amazon's mailbox simulator (never reaches a person, doesn't hurt reputation) - requires the explicit flag
.\Invoke-RastiSiLiveSesSmoke.ps1 -FromAddress info@yourdomain.com -Region eu-west-1 -ConfirmLiveSend
```
It uses *your* AWS credentials from your own environment/profile at run time (never stored, printed or committed). `Start-RastiSiQA.ps1` itself
has **no** live mode and clears every `AWS_*`/`RASTISI_SES_*` variable for its own process.
