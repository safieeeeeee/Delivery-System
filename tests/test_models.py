from delivery_system.models import Customer, Order, OrderItem


def test_customer_to_dict():
    customer = Customer(id=1, name="Иван", phone="+79990000000", address="Москва")

    assert customer.to_dict() == {
        "id": 1,
        "name": "Иван",
        "phone": "+79990000000",
        "address": "Москва",
    }


def test_order_calculates_total():
    order = Order(
        id=1,
        customer_id=1,
        order_date="2026-06-13",
        status="новый",
        items=[
            OrderItem(product_name="Пицца", quantity=2, price=750),
            OrderItem(product_name="Сок", quantity=1, price=120),
        ],
    )

    assert order.total == 1620

