from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional


ORDER_STATUSES = ("новый", "в доставке", "выполнен", "отменён")


def validate_order_date(order_date: str) -> None:
    try:
        datetime.strptime(order_date, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError("Дата заказа должна быть в формате YYYY-MM-DD") from exc


@dataclass
class Customer:
    id: Optional[int]
    name: str
    phone: str = ""
    address: str = ""

    def __post_init__(self) -> None:
        self.name = self.name.strip()
        self.phone = (self.phone or "").strip()
        self.address = (self.address or "").strip()
        if not self.name:
            raise ValueError("Имя клиента обязательно")

    def to_dict(self) -> Dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "phone": self.phone,
            "address": self.address,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, object]) -> "Customer":
        return cls(
            id=data.get("id"),
            name=str(data.get("name", "")),
            phone=str(data.get("phone", "")),
            address=str(data.get("address", "")),
        )


@dataclass
class OrderItem:
    id: Optional[int] = None
    order_id: Optional[int] = None
    product_name: str = ""
    quantity: int = 1
    price: float = 0.0

    def __post_init__(self) -> None:
        self.product_name = self.product_name.strip()
        if not self.product_name:
            raise ValueError("Название товара обязательно")

        try:
            self.quantity = int(self.quantity)
            self.price = float(self.price)
        except (TypeError, ValueError) as exc:
            raise ValueError("Количество и цена должны быть числами") from exc

        if self.quantity <= 0:
            raise ValueError("Количество товара должно быть больше нуля")
        if self.price < 0:
            raise ValueError("Цена товара не может быть отрицательной")

    @property
    def total(self) -> float:
        return round(self.quantity * self.price, 2)

    def to_dict(self) -> Dict[str, object]:
        return {
            "id": self.id,
            "order_id": self.order_id,
            "product_name": self.product_name,
            "quantity": self.quantity,
            "price": self.price,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, object]) -> "OrderItem":
        return cls(
            id=data.get("id"),
            order_id=data.get("order_id"),
            product_name=str(data.get("product_name", "")),
            quantity=data.get("quantity", 1),
            price=data.get("price", 0.0),
        )


@dataclass
class Order:
    id: Optional[int]
    customer_id: int
    order_date: str
    status: str = "новый"
    total: float = 0.0
    items: List[OrderItem] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.customer_id:
            raise ValueError("Клиент заказа обязателен")
        validate_order_date(self.order_date)
        if self.status not in ORDER_STATUSES:
            raise ValueError(f"Недопустимый статус заказа: {self.status}")
        if self.items:
            self.total = round(sum(item.total for item in self.items), 2)
        else:
            self.total = float(self.total)

    def to_dict(self, customer: Optional[Customer] = None) -> Dict[str, object]:
        data = {
            "id": self.id,
            "customer_id": self.customer_id,
            "order_date": self.order_date,
            "status": self.status,
            "total": self.total,
            "items": [item.to_dict() for item in self.items],
        }
        if customer is not None:
            data["customer"] = customer.to_dict()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, object]) -> "Order":
        items = [OrderItem.from_dict(item) for item in data.get("items", [])]
        return cls(
            id=data.get("id"),
            customer_id=int(data.get("customer_id", 0)),
            order_date=str(data.get("order_date", "")),
            status=str(data.get("status", "новый")),
            total=float(data.get("total", 0.0)),
            items=items,
        )

