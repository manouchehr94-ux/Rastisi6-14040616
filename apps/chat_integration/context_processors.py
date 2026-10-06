from . import conf
from .services import enablement, identity_service


def chat_permissions(request):
    """Flags for the merchant navigation: False everywhere unless the store has chat enabled AND the member's role may use it."""
    chat_global = conf.globally_enabled()
    membership = getattr(request, "store_membership", None)
    store = getattr(request, "store", None)
    if membership is None or not enablement.chat_enabled_for_store(store):
        return {"can_chat_customers": False, "can_chat_platform_support": False, "chat_global": chat_global}
    return {
        "can_chat_customers": identity_service.staff_role_for(membership, surface="customers") is not None,
        "can_chat_platform_support": identity_service.staff_role_for(membership, surface="platform_support") is not None,
        "chat_global": chat_global,
    }
