# Public website — new "Sardar" design, editable from Platform Admin

The public marketing website (`rastisi.ir`: `/`, `/features/`, `/design/`, `/plans/`, `/help/`,
`/about/`, `/contact/`, `/login/`, `/register/`, OTP/reset pages, `/terms/`, `/privacy/`,
`/supported-industries/`, 404) has a new visual design ("shop sign": Lalezar + Vazirmatn, green
sign / saffron price tags) that replaces the previous one **without changing any behaviour**:
the same views, forms, rate limits, Turnstile, OTP flows, plans-from-database and URLs.

## What changed (and what did not)

* New templates under `apps/portal/templates/portal/public_v2/`, CSS `portal/css/public-v2.css`,
  JS `portal/js/public-v2*.js`. The previous templates in `portal/public/` are **untouched** and
  remain the rollback path. (`terms.html` now includes `_terms_body.html` / `_terms_toc.html`, so the
  legal text has one source shared by both designs.)
* `apps/portal/views.py` imports `render` from `apps/portal/public_site/rendering.py`. It serves
  `portal/public_v2/<page>` when the new design is active and that template exists; otherwise the
  original `portal/public/<page>` — nothing else in the views changed (plus: the home view also passes
  `plan_rows`, and `/register/?phone=` only pre-fills the phone input).
* Storefronts / tenants / Store scoping / merchant admin: not touched.

## Editing from Platform Admin (superuser only)

Platform Admin → **متن و ظاهر سایت عمومی** (`/public-site/`):

| Group | Controls |
| --- | --- |
| رنگ‌ها و فونت‌ها | 14 colour tokens (light + dark), text/heading font (presets or custom family name + HTTPS font CSS URL), base font size |
| سربرگ، پاورقی و فراخوان پایانی | menu/footer/closing-CTA texts, social links |
| صفحه اصلی, امکانات, قالب‌ها, تعرفه‌ها, پرسش‌ها, درباره, تماس, ورود و ثبت‌نام, ۴۰۴ | every visible text; list items (FAQ, features, templates, receipt, ledger…) have a «hide» switch and spare slots |

Images stay in **تصاویر سایت عمومی** (now also the site logo; the platform's uploaded logo in
تنظیمات پلتفرم is used if no logo override exists).

Rules: empty or equal-to-default means "default" (the row is deleted); a single `-` means "show nothing".
Tokens inside texts: `{trial}` (default trial days from PlatformConfiguration), `{support_phone}`,
`{support_email}`. Plan names, prices, trial days and feature bullets always come from the real
Plan/PlanVersion records. Every save, reset and design switch is written to the platform audit log.

Data lives in `PublicSiteSetting` (overrides only) — an empty table renders the shipped design, so
nothing breaks if the table is empty or missing (deploy-before-migrate is safe).

## Rolling back — fastest first

1. **Panel** (≈ 5 s): Platform Admin → متن و ظاهر سایت عمومی → **بازگشت به طراحی قبلی**. Texts/colours are
   kept; click **طراحی جدید** to return.
2. **Environment** (no panel/DB needed): set `RASTISI_PUBLIC_SITE_DESIGN=legacy` and restart. It wins over
   the panel switch (`v2` forces the new design the same way).
3. **Git**: the whole change is on branch `landing-v2-sardar`; `git revert <merge commit>` removes it. The
   migration `0013_public_site_setting` only adds a table and widens a `choices` list, so no data migration
   is needed to revert.

## Deploy checklist

1. `python manage.py migrate` (portal `0013`).
2. `collectstatic` (new CSS/JS, `portal/fonts/Lalezar-Regular.ttf`, `portal/images/public/logo.webp`).
3. Open `/` and `/register/` on the platform host; check the trial-day figure in the texts matches
   Platform Admin → تنظیمات پلتفرم → روزهای پیش‌فرض دوره آزمایشی.
4. Fill the real contact details (تلفن/ایمیل in تنظیمات پلتفرم; hours/address in تماس با ما) — the
   contact page and footer show only what is configured; nothing is invented.
