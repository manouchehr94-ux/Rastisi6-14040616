"""گزارشِ قطعیِ کامل‌بودنِ همه‌یِ قالب‌هایِ صنف (آخرین نسخه‌یِ هر صنف).

بدونِ ``--apply`` فقط‌خواندنی است. با ``--apply`` آمادگیِ قالب‌ها با همان اعتبارسنج
هم‌گرا می‌شود (idempotent): قالبِ ساختاراً معتبر ولی اسکلتی → ``review_required`` و از
نصبِ جدید کنار می‌رود؛ قالبِ کامل → ``production_ready``. **هیچ نصبِ موجودِ Store حذف یا
بازنویسی نمی‌شود** (نصب = deep copy مستقل). ``deprecated``/``archived`` هرگز خودکار تغییر نمی‌کنند.

    python manage.py audit_industry_templates                       # جدولِ متنی
    python manage.py audit_industry_templates --format markdown --output docs/.../AUDIT.md
    python manage.py audit_industry_templates --format json
    python manage.py audit_industry_templates --apply               # هم‌گراکردنِ آمادگی
"""

import json
from pathlib import Path

from django.core.management.base import BaseCommand

from apps.catalog.models import IndustryTemplate
from apps.catalog.services import template_audit_service as audit
from apps.catalog.services.template_validation_service import validate_and_persist

_READINESS_FA = dict(IndustryTemplate.Readiness.choices)
_SECTOR_FA = dict(IndustryTemplate.Sector.choices)

_GAP_FA = {
    "COMPLETENESS_TOO_FEW_CATEGORIES": "دسته‌بندی کم",
    "COMPLETENESS_TOO_FEW_ATTRIBUTES": "ویژگی کم",
    "COMPLETENESS_TOO_FEW_MAPPINGS": "نگاشت کم",
    "COMPLETENESS_LOW_SCHEMA_COVERAGE": "پوششِ طرحِ ویژگی کم",
    "COMPLETENESS_NO_STRUCTURED_ATTRIBUTE": "بدونِ ویژگیِ انتخابی",
    "COMPLETENESS_NO_VARIANT_RECOMMENDATION": "بدونِ محورِ تنوع",
    "COMPLETENESS_SERVICE_TOO_FEW_CATEGORIES": "انواعِ خدمت کم",
}


class Command(BaseCommand):
    help = "گزارشِ قطعیِ کامل‌بودنِ قالب‌هایِ صنف؛ با --apply آمادگی را هم‌گرا می‌کند (نصب‌هایِ موجود دست‌نخورده)."

    def add_arguments(self, parser):
        parser.add_argument("--format", choices=["table", "json", "markdown"], default="table")
        parser.add_argument("--output", default=None, help="مسیرِ فایلِ خروجی (پیش‌فرض: stdout)")
        parser.add_argument("--apply", action="store_true", help="آمادگیِ قالب‌ها را با اعتبارسنج هم‌گرا کن")

    def handle(self, *args, **options):
        if options["apply"]:
            changed = 0
            for template in audit.latest_templates():
                before = template.readiness
                validate_and_persist(template)
                template.refresh_from_db(fields=["readiness"])
                changed += int(before != template.readiness)
            self.stderr.write(f"آمادگیِ {changed} قالب هم‌گرا شد (نصب‌هایِ موجود دست‌نخورده‌اند).")

        rows = audit.audit_latest_templates()
        summary = audit.summarize(rows)
        fmt = options["format"]
        text = (
            json.dumps({"summary": summary, "templates": rows}, ensure_ascii=False, indent=2, sort_keys=True)
            if fmt == "json" else self._markdown(rows, summary) if fmt == "markdown" else self._table(rows, summary)
        )
        if options["output"]:
            path = Path(options["output"])
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text + "\n", encoding="utf-8")
            self.stderr.write(f"گزارش در {path} نوشته شد.")
        else:
            self.stdout.write(text)

    # ---------------------------------------------------------------- renderers
    def _table(self, rows, summary):
        lines = [
            f"{r['slug']:<30} {r['sector']:<9} {r['stored_readiness']:<17} → {r['recommended_readiness']:<17} "
            f"c={r['category_count']:<2} a={r['attribute_count']:<2} m={r['mapping_count']:<3} q={r['quality_score']:<3} "
            f"{'OFFER' if r['offerable'] else '-'}  {','.join(r['review_gaps'])}"
            for r in rows
        ]
        lines.append("")
        lines.append(json.dumps(summary, ensure_ascii=False, sort_keys=True))
        return "\n".join(lines)

    def _markdown(self, rows, summary):
        out = [
            "# گزارشِ کامل‌بودنِ قالب‌هایِ صنف (Industry Template Completeness Audit)",
            "",
            "> تولیدشده با `python manage.py audit_industry_templates --format markdown` — قطعی (بدونِ زمان). "
            "فقط آخرین نسخه‌یِ هر صنف. معیارها: `apps/catalog/services/template_validation_service.py` و "
            "ADR-26 (addendum «Completeness gate»).",
            "",
            "## جمع‌بندی",
            "",
            f"- کل قالب‌ها (آخرین نسخه‌یِ هر صنف): **{summary['total']}**",
        ]
        for key, label in (("stored_readiness", "آمادگیِ ذخیره‌شده"), ("recommended_readiness", "آمادگیِ پیشنهادیِ اعتبارسنج")):
            parts = "، ".join(f"{_READINESS_FA.get(k, k)}: {v}" for k, v in summary[key].items())
            out.append(f"- {label}: {parts}")
        out += [
            f"- پیشنهادشونده برایِ نصبِ جدید (offerable): **{summary['offerable_now']}**",
            f"- نیازمندِ غنی‌سازیِ محتوا (backlog): **{summary['needs_enrichment']}**",
            "",
            "## معیارهایِ production_ready",
            "",
            "| پروفایل | رسته‌ها | شرط‌ها |",
            "|---|---|---|",
            "| product | خرده‌فروشی، دیجیتال، خوراک، خانه، سلامت و زیبایی، ورزش، فرهنگ، خودرو، صنعتی | "
            "≥۴ دسته، ≥۵ ویژگی، ≥۸ نگاشت، پوششِ طرحِ ویژگی (با ارثِ والد) ≥ نیمِ دسته‌هایِ برگ و ≥۲ دسته‌یِ نگاشت‌شده، ≥۱ ویژگیِ انتخابیِ دارایِ ≥۲ مقدار (نبودِ «قابل‌فیلتر» فقط هشدار است)؛ و برایِ «خرده‌فروشی» ≥۱ محورِ تنوعِ پیشنهادی |",
            "| service | خدمات | ≥۳ دسته (نوعِ خدمت)؛ ویژگیِ کالایی لازم نیست |",
            "| free_form | سایر | عمداً عمومی؛ فقط اعتبارِ ساختاری |",
            "",
            "## همه‌یِ قالب‌ها",
            "",
            "| slug | نام | رسته | ذخیره‌شده | پیشنهادی | امتیاز | دسته | ریشه | عمق | ویژگی | نگاشت | الزامی | فیلتر | تنوع | پیشنهاد | بخش | پیشنهادشونده | خلأها |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
        ]
        for r in rows:
            out.append(
                f"| `{r['slug']}` | {r['name']} | {_SECTOR_FA.get(r['sector'], r['sector'])} | "
                f"{_READINESS_FA.get(r['stored_readiness'])} | {_READINESS_FA.get(r['recommended_readiness'])} | "
                f"{r['quality_score']} | {r['category_count']} | {r['root_category_count']} | {r['max_category_depth']} | "
                f"{r['attribute_count']} | {r['mapping_count']} | {r['required_mapping_count']} | "
                f"{r['filterable_mapping_count']} | {r['variant_axis_count']} | {r['recommendation_count']} | "
                f"{r['default_section_count']} | {'✔' if r['offerable'] else '—'} | "
                f"{'، '.join(_GAP_FA.get(g, g) for g in r['review_gaps']) or '—'} |"
            )
        backlog = [r for r in rows if r["needs_enrichment"] or (r["review_gaps"] and r["stored_readiness"] != "deprecated")]
        out += ["", f"## فهرستِ غنی‌سازیِ محتوا (Backlog — {len(backlog)} قالب)", ""]
        current = None
        for r in backlog:
            if r["sector"] != current:
                current = r["sector"]
                out += ["", f"### {_SECTOR_FA.get(current, current)}", ""]
            out.append(f"- `{r['slug']}` — {r['name']}: {'، '.join(_GAP_FA.get(g, g) for g in r['review_gaps'])}")
        out += [
            "",
            "## یادداشت‌ها",
            "",
            "- قالب‌هایِ `deprecated` (منسوخِ فازِ پیشین) در backlog نیستند و پیشنهاد نمی‌شوند.",
            "- «سایر (صنف آزاد)» عمداً عمومی است و استثنایِ صریحِ معیار است.",
            "- نصب‌هایِ موجودِ Store هرگز با تغییرِ آمادگی حذف/بازنویسی نمی‌شوند.",
        ]
        return "\n".join(out)
