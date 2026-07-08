# Module 11 — Notifications Integration Contract

This contract defines the schemas, service function interfaces, indexing decisions, and cross-module interactions for the Notifications subsystem of GALXY.

---

## 1. Database Collections & Index Specs

### Collection: `notifications`
Stores the in-app notifications shown in the customer dashboard feed.

```json
{
  "_id": "ObjectId",
  "user_id": "ObjectId",
  "type": "String",
  "title": "String",
  "message": "String",
  "related_order_number": "String | null",
  "related_product_id": "ObjectId | null",
  "is_read": "Boolean",
  "created_at": "ISODate"
}
```

#### Indexing Strategy:
1. **Compound Index:** `{"user_id": 1, "is_read": 1}`
   * *Purpose:* Optimizes the frequent notification badge rendering and unread feed counts.
2. **Chronological Index:** `{"created_at": -1}`
   * *Purpose:* Speeds up pagination requests displaying newest-first alerts.

---

### Collection: `telegram_subscriptions`
Stores subscription links mapping customers to their Telegram chat channels.

```json
{
  "_id": "ObjectId",
  "user_id": "ObjectId",
  "chat_id": "String",
  "is_active": "Boolean",
  "linked_at": "ISODate"
}
```

#### Indexing Strategy:
1. **Unique Index:** `{"user_id": 1}` (Unique: True)
   * *Purpose:* Enforces that a customer only links one active chat handle at any time.

---

## 2. Core Service Interface

The entrypoint to the service layer is located inside [notification_service.py](../app/services/notification_service.py).

### A. Dispatching Alerts (`notify_user`)
Called by Module 8 (Orders), Module 9 (Reviews), and other triggers to persist and dispatch a notification.

```python
def notify_user(
    user_id, 
    notification_type, 
    title, 
    message, 
    related_order_number=None, 
    related_product_id=None, 
    send_email=False, 
    send_telegram=False
):
    """
    Creates an in-app notification.
    Optionally requests email and Telegram delivery.
    """
```

*   **`user_id`**: String or ObjectId of the target customer.
*   **`notification_type`**: String slug identifying the trigger (e.g. `order_created`, `order_status_changed`, `review_approved`).
*   **`title`**: Brief headline of the notification.
*   **`message`**: Readable paragraph of description.
*   **`related_order_number`** *(Optional)*: Order ID (e.g. `GLX-2026-00042`) if the notification relates to a purchase.
*   **`related_product_id`** *(Optional)*: Product ObjectID/String if it concerns specific merchandise.
*   **`send_email`** *(Default: False)*: Triggers the SMTP email delivery helper if True.
*   **`send_telegram`** *(Default: False)*: Triggers telegram client delivery to the user's active subscription if True.

---

### B. User Actions & Query APIs

#### `list_notifications(user_id, is_read=None, page=1, limit=20)`
Retrieves a paginated list of notifications. Returns the standardized paginated response structure:
```json
{
  "success": true,
  "data": [
    {
      "id": "string_id",
      "user_id": "string_user_id",
      "type": "string",
      "title": "string",
      "message": "string",
      "related_order_number": "string_or_null",
      "related_product_id": "string_or_null",
      "is_read": false,
      "created_at": "ISO-8601-String"
    }
  ],
  "page": 1,
  "limit": 20,
  "total": 1,
  "totalPages": 1
}
```

#### `mark_as_read(user_id, notification_id)`
Sets `is_read = true` for the specified notification ID matching `user_id`.

#### `mark_all_as_read(user_id)`
Bulk-sets `is_read = true` for all unread notifications belonging to the target customer.

#### `get_unread_count(user_id)`
Calculates the count of unread notifications for quick badge rendering.

---

## 3. Integration Guidelines for Other Modules

### Module 8 (Orders) Integration
Trigger a notification during checkout creation or when changing order status:
```python
from app.services.notification_service import notify_user

# 1. On New Order Inquiry Checkout:
notify_user(
    user_id=order["user_id"],
    notification_type="order_created",
    title="Inquiry Received!",
    message="We have received your custom order request. Asil is reviewing it.",
    related_order_number=order["order_number"],
    send_email=True
)

# 2. On Order Stage Transitions (e.g. Confirmed, Production):
notify_user(
    user_id=order["user_id"],
    notification_type="order_status_changed",
    title=f"Order status: {new_status.title()}",
    message=f"Your order {order['order_number']} is now: {new_status_description}.",
    related_order_number=order["order_number"],
    send_email=True,
    send_telegram=True  # Will send telegram if user has active subscription
)
```

### Module 9 (Reviews) Integration
Trigger when reviews are moderated and published:
```python
from app.services.notification_service import notify_user

# On review approval:
notify_user(
    user_id=review["user_id"],
    notification_type="review_approved",
    title="Review Approved!",
    message="Your review for this product has been approved and published. Thank you!",
    related_product_id=review["product_id"]
)
```

---

## 4. Subsystem Hooks (Ajay & Guru Dev)

*   **Ajay's Delivery Hooks:**
    *   **Email:** `notify_user` calls `send_email_notification(user_id, title, message)` if `send_email=True`.
    *   **Telegram:** `notify_user` checks `telegram_subscriptions`, and calls `send_telegram_notification(chat_id, title, message)` if subscription is active and `send_telegram=True`.
*   **Guru Dev's Route Hooks:**
    *   **Telegram Settings UI:** Utilize `subscribe_telegram(user_id, chat_id)` to link a subscription and `unsubscribe_telegram(user_id)` to deactivate it.
    *   **Notifications API:** Build standard routes mapping to:
        *   `GET /api/notifications` -> `list_notifications(user_id, is_read, page, limit)`
        *   `PUT /api/notifications/read-all` -> `mark_all_as_read(user_id)`
        *   `PUT /api/notifications/:id/read` -> `mark_as_read(user_id, id)`

---

## 5. Specification Deviations & Enhancements Changelog

The implementation deviates from `Galxy_Project_Plan (1).docx §3.12` with the following improvements approved by the project leads:

*   **Type Discriminator (`type`):** Added to distinguish triggers (e.g., `order_created`, `order_status_changed`, `review_approved`).
*   **Notification Title (`title`):** Added to provide a concise headline for alerts independent of the body message.
*   **Order Number Reference (`related_order_number`):** Changed from `order_id` string to `related_order_number` to align with the database schema of Module 8.
*   **Product ID Reference (`related_product_id`):** Added support for product-linked notifications (e.g., review approval notifications) requested by Module 9.

