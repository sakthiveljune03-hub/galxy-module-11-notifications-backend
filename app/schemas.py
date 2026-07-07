from typing import TypedDict


class Recipient(TypedDict, total=False):
    user_id: str
    email: str
    name: str
    customer_email: str


class OrderReceivedData(TypedDict, total=False):
    order_number: str
    estimated_total: float
    dashboard_url: str


class OrderStatusChangedData(TypedDict, total=False):
    order_number: str
    new_status: str
    note: str
    dashboard_url: str


class AdminNewOrderAlertData(TypedDict, total=False):
    order_number: str
    estimated_total: float
    admin_url: str


class GeneralNotificationData(TypedDict, total=False):
    subject: str
    message: str

