"""Safe eNamad technical-domain verification helpers.

The eNamad dashboard may ask a site owner to place a verification ``<meta>``
tag on the site's home page. We never render merchant/platform supplied HTML
verbatim. The submitted snippet is parsed, must consist of one plain ``meta``
element with exactly ``name`` and ``content`` attributes, and the two values
are rendered through Django's normal auto-escaping.
"""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
import re


class EnamadVerificationMetaError(ValueError):
    """The supplied technical-verification meta tag is unsafe or malformed."""


@dataclass(frozen=True)
class EnamadVerificationMeta:
    name: str
    content: str


_META_NAME_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_MAX_CONTENT_LENGTH = 1024


class _SingleMetaParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.elements: list[list[tuple[str, str | None]]] = []
        self.invalid = False

    def _accept(self, tag, attrs):
        if tag.lower() != "meta" or self.elements:
            self.invalid = True
            return
        self.elements.append(attrs)

    def handle_starttag(self, tag, attrs):
        self._accept(tag, attrs)

    def handle_startendtag(self, tag, attrs):
        self._accept(tag, attrs)

    def handle_endtag(self, tag):
        self.invalid = True

    def handle_data(self, data):
        if data.strip():
            self.invalid = True

    def handle_comment(self, data):
        self.invalid = True

    def handle_decl(self, decl):
        self.invalid = True

    def handle_pi(self, data):
        self.invalid = True


def parse_enamad_verification_meta_tag(raw: str) -> EnamadVerificationMeta | None:
    """Parse one safe ``<meta name="..." content="...">`` snippet."""
    raw = str(raw or "").strip()
    if not raw:
        return None

    parser = _SingleMetaParser()
    try:
        parser.feed(raw)
        parser.close()
    except Exception as exc:
        raise EnamadVerificationMetaError(
            "متاتگ اینماد قابل‌خواندن نیست."
        ) from exc

    if parser.invalid or len(parser.elements) != 1:
        raise EnamadVerificationMetaError(
            "فقط یک تگ meta ساده برای احراز اینماد مجاز است."
        )

    attrs = parser.elements[0]
    normalized: dict[str, str] = {}
    for key, value in attrs:
        key = (key or "").lower()
        if key not in {"name", "content"} or key in normalized or value is None:
            raise EnamadVerificationMetaError(
                "متاتگ اینماد فقط باید شامل دو ویژگی name و content باشد."
            )
        normalized[key] = value

    if set(normalized) != {"name", "content"}:
        raise EnamadVerificationMetaError(
            "متاتگ اینماد باید هر دو ویژگی name و content را داشته باشد."
        )

    name = normalized["name"].strip()
    content = normalized["content"].strip()

    if not _META_NAME_RE.fullmatch(name):
        raise EnamadVerificationMetaError(
            "مقدار name متاتگ اینماد معتبر نیست."
        )
    if not content:
        raise EnamadVerificationMetaError(
            "مقدار content متاتگ اینماد نمی‌تواند خالی باشد."
        )
    if len(content) > _MAX_CONTENT_LENGTH:
        raise EnamadVerificationMetaError(
            "مقدار content متاتگ اینماد بیش از حد طولانی است."
        )
    if any(ord(ch) < 32 and ch not in "\t\r\n" for ch in content):
        raise EnamadVerificationMetaError(
            "مقدار content متاتگ اینماد شامل نویسه‌ی کنترل نامعتبر است."
        )

    return EnamadVerificationMeta(name=name, content=content)


#: eNamad's own trust-seal host (https://trustseal.enamad.ir) — the *only*
#: origin the generated badge markup ever points to. Never user/DB-supplied.
TRUSTSEAL_BASE_URL = "https://trustseal.enamad.ir/"

_ENAMAD_ID_RE = re.compile(r"^[0-9]{1,12}$")
_ENAMAD_AUTH_CODE_RE = re.compile(r"^[A-Za-z0-9]{1,64}$")


class EnamadBadgeError(ValueError):
    """The supplied eNamad final-badge identifiers are missing/invalid."""


@dataclass(frozen=True)
class EnamadBadgeIdentifiers:
    enamad_id: str
    auth_code: str

    @property
    def profile_url(self) -> str:
        return f"{TRUSTSEAL_BASE_URL}?id={self.enamad_id}&Code={self.auth_code}"

    @property
    def logo_url(self) -> str:
        return f"{TRUSTSEAL_BASE_URL}logo.aspx?id={self.enamad_id}&Code={self.auth_code}"


def parse_enamad_badge_identifiers(enamad_id: str, auth_code: str) -> EnamadBadgeIdentifiers | None:
    """Validate the two *structured* identifiers eNamad issues once a Store's
    (or the platform's) trust seal has actually been granted — never a raw
    HTML/script fragment. Both must be present together; either both blank
    returns ``None`` (not configured yet, not an error)."""
    enamad_id = str(enamad_id or "").strip()
    auth_code = str(auth_code or "").strip()

    if not enamad_id and not auth_code:
        return None
    if not enamad_id or not auth_code:
        raise EnamadBadgeError(
            "برای نمایشِ نمادِ نهایی، هم «شناسه» و هم «کدِ تأیید» اینماد لازم است."
        )
    if not _ENAMAD_ID_RE.fullmatch(enamad_id):
        raise EnamadBadgeError("شناسه‌ی اینماد باید فقط شامل رقم باشد.")
    if not _ENAMAD_AUTH_CODE_RE.fullmatch(auth_code):
        raise EnamadBadgeError("کدِ تأییدِ اینماد نامعتبر است.")
    return EnamadBadgeIdentifiers(enamad_id=enamad_id, auth_code=auth_code)


def validate_enamad_integration_values(values: dict) -> str | None:
    """Allow the pre-issuance meta tag and/or the post-issuance structured
    badge identifiers — independently of each other. Never accepts a raw
    HTML/script fragment for the badge; only the two eNamad-issued
    identifiers, from which trusted markup is generated server-side."""
    meta_tag = str(values.get("verification_meta_tag") or "").strip()
    enamad_id = str(values.get("enamad_id") or "").strip()
    auth_code = str(values.get("enamad_auth_code") or "").strip()

    if not meta_tag and not enamad_id and not auth_code:
        return "متاتگ احراز فنی یا شناسه/کدِ نمادِ اینماد را وارد کنید."

    if meta_tag:
        try:
            parse_enamad_verification_meta_tag(meta_tag)
        except EnamadVerificationMetaError as exc:
            return str(exc)

    if enamad_id or auth_code:
        try:
            parse_enamad_badge_identifiers(enamad_id, auth_code)
        except EnamadBadgeError as exc:
            return str(exc)

    return None


def _store_owns_verified_custom_domain(request, *, store_id: int) -> bool:
    """True only when the current request's Host is *this exact* Store's own
    verified custom domain — never a trial/platform subdomain, never
    another Store's domain. Shared by both the technical-meta and the
    final-badge renderers so their tenant/host scoping can never drift
    apart."""
    try:
        host = request.get_host().split(":", 1)[0].lower().rstrip(".")
    except Exception:
        return False
    if not host:
        return False

    from apps.stores.models import StoreDomain

    return StoreDomain.objects.filter(
        store_id=store_id,
        hostname=host,
        domain_type=StoreDomain.DomainType.CUSTOM_DOMAIN,
        verification_status=StoreDomain.VerificationStatus.VERIFIED,
        retired_at__isnull=True,
    ).exists()


def _store_enamad_connection(store_id: int):
    from apps.stores.models import StoreIntegrationConnection

    return (
        StoreIntegrationConnection.objects
        .filter(store_id=store_id, provider_code="enamad", is_active=True)
        .only("encrypted_credentials")
        .first()
    )


def store_enamad_verification_meta_for_request(
    request, *, store_id: int
) -> EnamadVerificationMeta | None:
    """Expose the merchant meta only on that Store's verified custom homepage."""
    if getattr(request, "path", "") != "/":
        return None
    if not _store_owns_verified_custom_domain(request, store_id=store_id):
        return None

    connection = _store_enamad_connection(store_id)
    if connection is None:
        return None

    raw = connection.get_credentials().get("verification_meta_tag", "")
    try:
        return parse_enamad_verification_meta_tag(raw)
    except EnamadVerificationMetaError:
        return None


def store_enamad_badge_for_request(
    request, *, store_id: int
) -> EnamadBadgeIdentifiers | None:
    """Expose the merchant's final, issued eNamad badge — independent of
    the technical-verification meta's state (a Store may have one, both,
    or neither at any time) — sitewide (not home-page-only, matching how
    a trust badge is normally displayed), but still only on that exact
    Store's own verified custom domain. A corrupt/legacy stored value
    fails closed (returns ``None``), never raises into the template."""
    if not _store_owns_verified_custom_domain(request, store_id=store_id):
        return None

    connection = _store_enamad_connection(store_id)
    if connection is None:
        return None

    credentials = connection.get_credentials()
    try:
        return parse_enamad_badge_identifiers(
            credentials.get("enamad_id", ""), credentials.get("enamad_auth_code", ""),
        )
    except EnamadBadgeError:
        return None


def store_has_verified_custom_domain(store) -> bool:
    """The only place the meta tag and the final badge ever render (see ``_store_owns_verified_custom_domain``): a VERIFIED, not retired custom
    domain of THIS store. Used by the Studio/settings page to say honestly where — and whether — the seal can appear."""
    from apps.stores.models import StoreDomain

    return StoreDomain.objects.filter(
        store=store, domain_type=StoreDomain.DomainType.CUSTOM_DOMAIN,
        verification_status=StoreDomain.VerificationStatus.VERIFIED, retired_at__isnull=True,
    ).exists()


def enamad_flow(store, credentials: dict, *, connected: bool) -> dict:
    """The two real stages of the eNamad flow as plain data, each computed from what is stored and where it would render.

    Stage 1 — «احراز دسترسی فنی»: the technical meta eNamad gives while it checks the site (``verification_meta_tag``). Rendered ONLY in the
    ``<head>`` of the home page of the store's own verified custom domain.
    Stage 2 — «نمادِ صادرشده»: the id + code eNamad shows AFTER it granted the seal. RastiSi builds the image and link itself; shown sitewide in the
    footer trust area, ONLY on the store's own verified custom domain.

    Saving either never means «approved»: RastiSi cannot ask eNamad (no official API), so no state here is ever «تأییدشده»."""
    verified_domain = store_has_verified_custom_domain(store)
    meta_raw = str(credentials.get("verification_meta_tag") or "").strip()
    badge_id = str(credentials.get("enamad_id") or "").strip()
    badge_code = str(credentials.get("enamad_auth_code") or "").strip()

    def _stage(key, title, hint, saved, error, where):
        if not saved:
            state, text = "empty", "هنوز ذخیره نشده است."
        elif error:
            state, text = "invalid", error
        elif not connected:
            state, text = "paused", "ذخیره شده ولی خاموش است؛ نمایش داده نمی‌شود."
        elif not verified_domain:
            state, text = "waiting_domain", "ذخیره شد؛ پس از تأیید دامنهٔ اختصاصی شما " + where + " قرار می‌گیرد."
        else:
            state, text = "ready", "ذخیره شد و " + where + " دامنهٔ اختصاصی شما قرار می‌گیرد."
        return {"key": key, "title": title, "hint": hint, "state": state, "text": text}

    meta_error = badge_error = ""
    if meta_raw:
        try:
            parse_enamad_verification_meta_tag(meta_raw)
        except EnamadVerificationMetaError as exc:
            meta_error = str(exc)
    if badge_id or badge_code:
        try:
            parse_enamad_badge_identifiers(badge_id, badge_code)
        except EnamadBadgeError as exc:
            badge_error = str(exc)
    return {
        "verified_domain": verified_domain,
        "stages": [
            _stage("meta", "مرحلهٔ ۱ — احراز دسترسی فنی (متاتگ)",
                   "اینماد هنگام بررسی سایت شما یک متاتگ می‌دهد. آن را اینجا بگذارید تا روی صفحهٔ اصلی سایت قرار بگیرد. این مرحله فقط «مالکیت/دسترسی» را نشان می‌دهد، نه صدور نماد.",
                   bool(meta_raw), meta_error, "در بخش <head> صفحهٔ اصلیِ"),
            _stage("badge", "مرحلهٔ ۲ — نمادِ صادرشده (شناسه و کد تأیید)",
                   "فقط پس از اینکه اینماد نماد را صادر کرد، شناسه و کد تأییدی را که نشان می‌دهد وارد کنید. راستی‌سی خودش تصویر و پیوند امن را می‌سازد.",
                   bool(badge_id or badge_code), badge_error, "در بخش نمادهای اعتماد فوترِ همهٔ صفحه‌های"),
        ],
        "limit_text": "راستی‌سی از اینماد استعلام نمی‌گیرد (سرویس رسمی برای این کار در اختیار ندارد)؛ پس ذخیره‌کردن شناسه هرگز به معنی «اینماد تأییدشده» نیست. وضعیت واقعیِ نماد را در پنل اینماد ببینید.",
        "display_text": ("نمایش فقط روی دامنهٔ اختصاصیِ تأییدشدهٔ همین فروشگاه انجام می‌شود." if verified_domain
                         else "فعلاً دامنهٔ اختصاصیِ تأییدشده‌ای ندارید؛ تا آن زمان نه متاتگ و نه نماد روی سایت قرار نمی‌گیرد."),
    }
