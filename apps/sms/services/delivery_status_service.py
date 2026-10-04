"""وضعیتِ یکپارچه‌ی ارسالِ پیامکِ یک فروشگاه — تنها منبعِ «کدام روش، سالم است یا نه» برایِ داشبوردِ مدیر و
``verify_delivery_channels`` (هر دو دقیقاً همان تصمیمِ زمانِ اجرا را می‌خوانند: ``ShopSettings.sms_delivery_method`` →
``sms_service.get_backend``). هیچ صف/دفتر/پیکربندیِ تازه‌ای نمی‌سازد؛ فقط می‌خواند.

دو روش (انتخابِ مالکِ فروشگاه): ``phone`` = گیت‌وی اندرویدِ SmsRasti (سیم‌کارتِ خودِ فروشگاه، بدونِ مصرفِ اعتبارِ
پلتفرم)، ``platform`` = درگاهِ مرکزیِ پلتفرم (اعتبارِ پیامک). OTP و پیامک‌هایِ امنیتی همیشه از درگاهِ مرکزی می‌روند."""

from datetime import timedelta

from django.utils import timezone

from apps.core.models import ShopSettings

DEVICE_ONLINE_WINDOW = timedelta(minutes=5)
LOW_CREDIT = 20


def get_sms_delivery_status(store, *, now=None) -> dict:
    from apps.notifications.models import NotificationOutbox as N
    from apps.portal.services.owner_sms_service import describe_platform_backend
    from apps.sms.models import SmsBalance, SmsLog, SmsOutboxItem

    now = now or timezone.now()
    shop = ShopSettings.load(store=store)
    method = shop.sms_delivery_method
    errors: list[str] = []
    warnings: list[str] = []

    queue = {s: SmsOutboxItem.objects.filter(store=store, status=s).count() for s in SmsOutboxItem.Status.values}
    notif = {
        s: N.objects.filter(store=store, channel=N.Channel.SMS, status=s).count()
        for s in (N.Status.PENDING, N.Status.FAILED, N.Status.DEAD)
    }
    failed_24h = SmsLog.objects.filter(store=store, status=SmsLog.Status.FAILED, created_at__gte=now - timedelta(hours=24)).count()
    credits = SmsBalance.objects.filter(store=store).values_list("credits", flat=True).first() or 0

    platform = describe_platform_backend()
    device = {"paired": bool(shop.smsrasti_device_token), "last_seen_at": shop.smsrasti_last_seen_at, "online": False}
    if shop.smsrasti_last_seen_at:
        device["online"] = now - shop.smsrasti_last_seen_at <= DEVICE_ONLINE_WINDOW

    if not shop.sms_enabled:
        errors.append("سیستم پیامک خاموش است؛ هیچ پیامکی ارسال نمی‌شود.")

    if method == "phone":
        if not device["paired"]:
            errors.append("دستگاهِ اسمس‌راستی هنوز جفت نشده است؛ در «تنظیمات پیامک» توکن بسازید و در اپ وارد کنید.")
        elif shop.smsrasti_last_seen_at is None:
            errors.append("دستگاه تا کنون به سرور وصل نشده است؛ اپِ اسمس‌راستی را باز کنید و توکن را وارد کنید.")
        elif not device["online"]:
            msg = "دستگاهِ اسمس‌راستی آفلاین است (آخرین اتصال بیش از ۵ دقیقه پیش)."
            if queue["pending"] or queue["sending"]:
                msg += f" {queue['pending'] + queue['sending']} پیام در صف منتظرِ اتصال است."
            warnings.append(msg)
        if queue["failed"]:
            warnings.append(f"{queue['failed']} پیامِ صفِ دستگاه ناموفق است؛ از گزارشِ پیامک‌ها دوباره صف کنید.")
        # OTP/امنیتی همچنان از درگاهِ مرکزی و اعتبارِ پلتفرم می‌رود
        if not platform["real"] or platform["problems"]:
            warnings.append("کدهای ورود (OTP) از درگاهِ مرکزیِ پلتفرم می‌رود و آن درگاه مشکل دارد: " + "؛ ".join(platform["problems"]))
    else:
        for problem in platform["problems"]:
            errors.append(f"درگاهِ مرکزیِ پلتفرم: {problem} (توسط پشتیبانی پلتفرم باید رفع شود).")
        if credits <= 0:
            errors.append("اعتبارِ پیامک تمام شده است؛ پیام‌ها ارسال نمی‌شوند. یک بسته‌ی اعتبار بخرید یا روشِ «گوشی» را انتخاب کنید.")
        elif credits < LOW_CREDIT:
            warnings.append(f"اعتبارِ پیامک کم است ({credits}).")

    if failed_24h:
        warnings.append(f"{failed_24h} پیامک در ۲۴ ساعتِ گذشته ناموفق بوده است (گزارشِ پیامک‌ها).")
    if notif[N.Status.DEAD]:
        warnings.append(f"{notif[N.Status.DEAD]} اعلانِ پیامکی پس از چند تلاش ناموفقِ نهایی شده است.")

    return {
        "enabled": shop.sms_enabled,
        "method": method,
        "method_label": "گوشیِ شما (اسمس‌راستی)" if method == "phone" else "درگاهِ مرکزیِ پلتفرم",
        "health": "error" if errors else "warning" if warnings else "ok",
        "errors": errors,
        "warnings": warnings,
        "credits": credits if method == "platform" else None,   # فقط وقتی اعتبار «به‌کار می‌آید»
        "platform_credits": credits,
        "device": device,
        "queue": queue,
        "notification_queue": notif,
        "failed_24h": failed_24h,
        "platform": platform,
    }
