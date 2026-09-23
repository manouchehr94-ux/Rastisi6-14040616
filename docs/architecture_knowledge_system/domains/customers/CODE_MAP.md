# customers — Code Map

```
domain_id: D3
code_baseline: 5883a140
```

```
apps/customers/
├── models.py               9 models (Customer[global], CustomerProfile[store-scoped], CustomerTag,
│                           CustomerNote, CustomerSegment(+Rule/+Membership), Address, Wishlist)
├── services/auth_service.py  signup / create_account_for_guest / authenticate_* / merge_guest_cart
├── urls.py                 account/login/signup/otp/profile/addresses/orders/wishlist
├── views.py
├── forms.py
├── context_processors.py   wishlist_membership, auth_forms
├── migrations/
└── tests/                  test_auth_service, test_auth_views

# CRM operations (cross-domain writers) live in:
apps/dashboard/services/customer_crm_service.py   profile stats / notes / tags
apps/dashboard/services/segment_service.py        segment rule engine
```

## Where to look
| Concern | File |
|---|---|
| Customer auth | `services/auth_service.py` |
| Guest→user cart merge | `services/auth_service.py::merge_guest_cart` |
| CRM (profiles/tags/notes) | `apps/dashboard/services/customer_crm_service.py` |
| Segments | `apps/dashboard/services/segment_service.py` |
| Global vs store-scoped | `models.py` (Customer vs CustomerProfile) |
