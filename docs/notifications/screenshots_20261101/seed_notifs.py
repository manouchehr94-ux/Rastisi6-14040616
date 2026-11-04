from datetime import timedelta
from django.contrib.auth import get_user_model
from django.utils import timezone
from apps.stores.models import Store
from apps.orders.models import Order
from apps.notifications.services import inbox_engine as eng, admin_events as ae
from apps.notifications.models import NotificationEvent, InboxItem
U = get_user_model()
store = Store.objects.get(slug="rastisi-fashion-test")
class _O:
    def __init__(s, code, pk): s.code, s.pk = code, pk
orders = list(Order.objects.filter(store=store).order_by("-id")[:6]) or [_O(f"DM-{10230 + i}", i + 1) for i in range(6)]
print("orders", [o.code for o in orders])
NotificationEvent.objects.filter(scope_key__in=[f"store:{store.pk}", "platform"]).delete()
plat, _ = U.objects.get_or_create(username="qa-platform-admin", defaults={"is_staff": True, "is_superuser": True})
plat.set_password("qa-pass-12345"); plat.save()
now = timezone.now()
def make(key, *, title, summary="", ago=0, **kw):
    ev = eng.publish(key, store=store, title=title, summary=summary, **kw)
    if ev and ago:
        t = now - timedelta(minutes=ago)
        NotificationEvent.objects.filter(pk=ev.pk).update(occurred_at=t)
        InboxItem.objects.filter(event=ev).update(created_at=t)
    return ev
for i, o in enumerate(orders[:3]):
    make("order.created", title=f"سفارش جدید {o.code}", summary="مبلغ ۲٬۴۵۰٬۰۰۰ تومان", entity=("Order", o.pk), link_kwargs={"code": o.code}, dedupe_key=f"qa-o{i}", ago=3 + i * 40)
if orders:
    make("order.canceled", title=f"سفارش {orders[3 % len(orders)].code} لغو شد", entity=("Order", 1), link_kwargs={"code": orders[3 % len(orders)].code}, dedupe_key="qa-c1", ago=130)
make("payment.suspicious", title="پرداخت مشکوک / مغایرت نیازمند رسیدگی", summary="سفارش با مبلغ گزارش‌شده‌ی نامتناسب از درگاه", dedupe_key="qa-s1", ago=12, severity=4)
make("stock.low", title="موجودی کم شد", summary="کیف چرم زیتونی — ۳ عدد مانده", dedupe_key="qa-st", group_key="qa-stock", ago=75)
for n in range(3):
    make("review.pending", title="نظر جدید نیازمند بررسی", summary="برای «کیف چرم زیتونی»", group_key="qa-rv", ago=300)
make("staff.role_changed", title="نقش یک عضو تغییر کرد", summary="«۰۹۱۲۰۰۰۰۰۰۰۳» اکنون «مدیر محتوا» است.", dedupe_key="qa-r1", ago=1500)
make("domain.verification_failed", title="تأیید دامنه هنوز انجام نشد", summary="shop.example.ir: رکورد DNS پیدا نشد.", group_key="qa-dom", ago=2900)
# mark a few read, pin one, snooze one
items = list(InboxItem.objects.filter(user__username="09120000002").order_by("id"))
for it in items[:2]:
    it.read_at = now
    it.save(update_fields=["read_at"])
if len(items) > 6:
    items[5].pinned = True; items[5].save(update_fields=["pinned"])
ev = eng.publish("platform.store_created", title="فروشگاه جدید ساخته شد", summary="فروشگاه نمونه‌ی آزمایشی", dedupe_key="qa-pl1")
eng.publish("platform.contact_message", title="پیام جدید از فرم تماس", summary="یک پیام تازه در انتظار بررسی است.", group_key="contact")
eng.publish("platform.jobs_unhealthy", title="کارهای زمان‌بندی‌شده مشکل دارند", summary="notification_backlog", dedupe_key="qa-jobs", severity=4)
print("unread", InboxItem.objects.filter(user__username="09120000002", read_at__isnull=True).count(), "platform items", InboxItem.objects.filter(user=plat).count())
