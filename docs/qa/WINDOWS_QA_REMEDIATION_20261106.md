# Isolated Windows QA for the remediation branch — instructions

**Not executed on Windows.** Everything below was prepared on Linux; nothing here has been run on your machine, so "Windows QA passed" must not be claimed until you do it.
The commands only **create new** things (a new folder, a new database, a new port). They never touch `QA_UNIFIED_FINAL_20261104`, `QA_PRICING_20261105`, `QA_ADMINUX_FINANCE_20261105`,
`V5_RUNTIME\qa_adminux_finance_20261105` or port `18083`. Nothing is pushed, merged or deployed, and the production server is never contacted.

## What you receive
`rastisi_remediation_20261106.bundle` (about 100 KB): the new local commits on top of the already-pushed `dev/platform-checkout-unify-20261106` (`8ad4b687…`).
It contains the branch `qa/integrated-remediation-20261106` (checkout + tenant isolation + simple pricing + Platform/Merchant/public UX) and the three source branches.

## 1. Create a new, empty folder and fetch the code
```powershell
$QA = "D:\Projects\RastiSi\QA_REMEDIATION_20261106"
if (Test-Path $QA) { throw "$QA already exists - pick another name. Nothing was changed." }
git clone https://github.com/manouchehr94-ux/Rastisi6-14040616 $QA
Set-Location $QA
git checkout dev/platform-checkout-unify-20261106          # the branch that is already on GitHub
git rev-parse HEAD                                          # must print 8ad4b6879859cc97b854108a7436f5d5fc026a8d
```
Put the bundle somewhere outside the project, then:
```powershell
$B = "D:\Projects\RastiSi\_incoming\rastisi_remediation_20261106.bundle"
git bundle verify $B                                        # must say "is okay"
git fetch $B "qa/integrated-remediation-20261106:qa/integrated-remediation-20261106"
git checkout qa/integrated-remediation-20261106
git rev-parse HEAD                                          # compare with the SHA in REMEDIATION_FINAL_REPORT_20261106.md
git status --short                                          # must be empty
```

## 2. Use the shared virtual environment (read-only use) and a brand-new database
```powershell
$PY = "D:\Projects\RastiSi\V5_VENV\Scripts\python.exe"
& $PY --version                                             # note it: the SMTP test needs Python 3.12+ compatibility (see report), older versions work too
& $PY -m pip install -r requirements.txt                    # only if the shared venv lacks a package; skip if you do not want to change it
```
*Database.* With `DATABASE_URL` **unset** the app creates `db.sqlite3` inside the new folder - already isolated and gitignored. For PostgreSQL create a **new** database first and point at it:
```powershell
# SQLite (simplest): nothing to set.
# PostgreSQL (optional):  $env:DATABASE_URL = "postgres://USER:PASSWORD@localhost:5432/rastisi_qa_remediation_20261106"
$env:DJANGO_DEBUG = "True"                                  # local QA only
& $PY manage.py migrate
& $PY manage.py makemigrations --check --dry-run            # must say: No changes detected
& $PY manage.py ensure_industry_registry --apply            # loads the industry registry (107 templates)
```

## 3. Create a throw-away platform-staff user (synthetic data only)
```powershell
@"
from django.contrib.auth import get_user_model
U = get_user_model()
U.objects.create_user(username="qa-staff@example.com", password="CHANGE-ME-throwaway-123", is_staff=True, is_superuser=True)
print("staff user created")
"@ | & $PY manage.py shell
```

## 4. Start the server on a NEW port
```powershell
& $PY manage.py runserver 127.0.0.1:18090
```
Open `http://platformadmins.rastisi.localhost:18090/` (Chrome/Edge resolve `*.localhost`; if yours does not, add `127.0.0.1 platformadmins.rastisi.localhost rastisi.localhost` to the hosts file).
Public site: `http://rastisi.localhost:18090/`.

## 5. What to look at (each line maps to the report)
| Area | Where | Expect |
|---|---|---|
| Industries table | `/industries/` | rows, separators and the slug column aligned on one line |
| Filter bars | `/payments/transactions/`, `/stores/`, `/domains/` | label row and control row aligned; buttons on their own row |
| Transactions | `/payments/transactions/` | empty state is correct on a fresh DB; pagination reaches the full history |
| Plan pricing | `/plans/add/` | one monthly price + 3 discount fields; instant preview (1,000 → 2,850 / 5,400 / 10,200); invalid discount rejected |
| Password fields | public `/login/`, Platform Admin login, gateway/SMS credential fields | eye icon inside the right edge, typing starts from the left |
| Date pickers | `/stores/` (filter), `/features/add/`, a store's "trial end" dialog | the whole calendar visible, never cut by a card/dialog; Escape closes it |
| Public design page | `rastisi.localhost:18090/design/` | 19 templates (same as the Studio gallery), compact header band |
| Privacy | `/privacy/` | draft notice, amber "needs owner confirmation" markers, `noindex` |
| Header search hint | merchant admin top bar | "Ctrl K" on one line |
Use only synthetic data. Do **not** enter real bank, SMS or email credentials.

## 6. Roll back (removes only what you created)
```powershell
Set-Location D:\Projects\RastiSi
Remove-Item -Recurse -Force "D:\Projects\RastiSi\QA_REMEDIATION_20261106"     # check the path first
```
