# Telegram Delivery Contract — Module 11

## Owner
**Ajay (GLX-M11-AJA-W2)** — Telegram integration alongside existing email delivery

## Scope (v1)
- Send transactional messages via Telegram Bot API for: `order_received`, `order_status_changed`, `general`
- Send admin alert to Asil on new order creation via Telegram (alongside email, never instead of)
- Non-blocking, best-effort delivery
- Failures are logged and never roll back the caller's operation

## Out of Scope (v1)
- SMS or push notification delivery (same as email scope boundary)
- Owned bot infrastructure (uses public Telegram Bot API)

## Configuration (Environment Variables)

| Variable | Required | Default | Description |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Yes | `""` | Bot token from @BotFather |
| `TELEGRAM_ADMIN_CHAT_ID` | Yes | `""` | Asil's chat ID for admin alerts |
| `TELEGRAM_API_BASE_URL` | No | `https://api.telegram.org` | API base URL override — ⚠ must only ever be set by trusted deployment configuration; the bot token is interpolated into every request URL sent to this host |

## Integration Points

### Telegram Subscriptions (Sakthivel — Module 11 Coordination Lead)
The service reads from the `telegram_subscriptions` collection (MongoDB) to resolve a user's active `chat_id`. Expected document shape:

```json
{
  "user_id": "ObjectId",
  "chat_id": "123456789",
  "is_active": true,
  "created_at": "ISO timestamp"
}
```

### Linking Endpoint (Guru Dev)
Guru Dev's linking endpoint writes into the same `telegram_subscriptions` collection — this service only reads it.

### Notify Hook (Sakthivel)
Telegram delivery functions are called from Sakthivel's `notify_user()` when `send_telegram=True`.

### Admin Alert (Module 8)
`send_admin_new_order_alert_telegram()` is called from `order_service.checkout()` alongside the email alert — never instead of it.

## API Surface

All public functions accept a `subscriptions_collection` (MongoDB collection reference) for chat ID resolution. Every function returns `bool` — `True` on success, `False` on failure (never raises).

### `send_order_received_telegram(user_id, customer_name, order_number, estimated_total, subscriptions_collection)`
Sends order confirmation via Telegram.

### `send_order_status_changed_telegram(user_id, customer_name, order_number, new_status, note, subscriptions_collection)`
Sends status update. `note` is optional.

### `send_admin_new_order_alert_telegram(customer_name, customer_email, order_number, estimated_total)`
Sends new-order alert to Asil's configured admin chat. Uses `TELEGRAM_ADMIN_CHAT_ID` env var directly — no subscription lookup needed.

### `send_telegram_message(chat_id, text)`
Low-level send. Markdown parse mode enabled for formatting.

### `get_user_chat_id(user_id, subscriptions_collection)`
Looks up the most recent active subscription for a user.

## Error Handling
- Every API call is wrapped in `try/except`
- Failures are logged with full traceback via `logging.error`
- Return `False` on failure — caller **must not** await or roll back
- Missing `TELEGRAM_BOT_TOKEN` logs a warning and returns `False`

## Templates
Templates live in `TELEGRAM_TEMPLATES` dict inside `telegram_delivery_service.py`.
- Markdown-formatted messages with emoji prefixes
- Template keys: `order_received`, `order_status_changed`, `admin_new_order_alert`, `general`
- Messages use `str.format()` with named placeholders
