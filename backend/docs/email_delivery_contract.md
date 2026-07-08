# Email Delivery Contract — Module 11

## Owner
**Ajay (GLX-M11-AJA-W2)** — Email Delivery, SMTP Integration & Admin Alerting Engineer

## Scope (v1)
- Send templated transactional emails for: `order_received`, `order_status_changed`, `general`
- Send admin alert to Asil on new order creation
- Fire-and-forget, non-blocking delivery
- Failures are logged and never roll back the caller's operation

## Out of Scope (v1)
- SMS or push notification delivery
- Full admin notification dashboard or history
- Owned/duplicated SMTP credentials (reuses Module 1's shared config)

## Integration Points

### SMTP Helper (Module 1)
The email service receives the SMTP sender as a **callable dependency** injected at call time.
Expected signature:

```python
def smtp_sender(to: str, subject: str, body_html: str) -> None:
    ...
```

Location: `app/utils/email_helper.py` (Module 1 owned)

### Notify Hook (Sakthivel — Module 11 Coordination Lead)
`email_delivery_service` functions are called from Sakthivel's `notify_user()` when `send_email=True`.

### Admin Alert Trigger (Module 8)
`send_admin_new_order_alert()` is called from `order_service.checkout()` after the order is persisted.

## API Surface

All public functions accept an `smtp_sender` callable as the last argument, so the caller provides the wired SMTP helper. Every function returns `bool` — `True` on successful send, `False` on failure (never raises).

### `send_order_received_email(user_email, customer_name, order_number, estimated_total, dashboard_url, smtp_sender)`
Sends order confirmation to the customer.

### `send_order_status_changed_email(user_email, customer_name, order_number, new_status, note, dashboard_url, smtp_sender)`
Sends status update notification. `note` is optional (customer-visible message from admin).

### `send_general_notification_email(to, subject, message, smtp_sender)`
Sends a free-form notification.

### `send_admin_new_order_alert(admin_email, customer_name, customer_email, order_number, estimated_total, admin_url, smtp_sender)`
Sends new-order alert to Asil's configured admin email.

## Error Handling
- Every send is wrapped in `try/except`
- Failures are logged with full traceback via `logging.error`
- Return `False` on failure — caller **must not** await or roll back
- No retry logic in v1

## Templates
Templates live in `EMAIL_TEMPLATES` dict inside `email_delivery_service.py`.
- Dark-themed HTML matching Galxy's brand (void black background, neon accents)
- Template keys: `order_received`, `order_status_changed`, `admin_new_order_alert`, `general`
- Subject lines and HTML bodies use `str.format()` with named placeholders
