from datetime import date

import pytest

from delivery_system.database import SQLiteDatabase
from delivery_system.models import OrderItem


@pytest.fixture()
def database(tmp_path):
    db = SQLiteDatabase(tmp_path / "delivery.db")
    yield db
    db.close()


def make_customer(database):
    return database.add_customer("Иван", "+79990000000", "Москва")


def make_order(database, customer_id, status="новый", order_date="2026-06-13"):
    return database.add_order(
        customer_id=customer_id,
        order_date=order_date,
        status=status,
        items=[OrderItem(product_name="Пицца", quantity=2, price=750)],
    )


def test_create_customer(database):
    customer = make_customer(database)

    assert customer.id is not None
    assert database.get_customer(customer.id).name == "Иван"


def test_create_order(database):
    customer = make_customer(database)
    order = make_order(database, customer.id)

    assert order.id is not None
    assert order.total == 1500
    assert order.items[0].product_name == "Пицца"


def test_cannot_delete_customer_with_orders(database):
    customer = make_customer(database)
    make_order(database, customer.id)

    with pytest.raises(ValueError, match="Нельзя удалить клиента"):
        database.delete_customer(customer.id)


def test_filter_orders_by_status(database):
    customer = make_customer(database)
    make_order(database, customer.id, status="новый")
    make_order(database, customer.id, status="выполнен")

    orders = database.list_orders(status="выполнен")

    assert len(orders) == 1
    assert orders[0].status == "выполнен"


def test_report_by_status(database):
    customer = make_customer(database)
    make_order(database, customer.id, status="новый")
    make_order(database, customer.id, status="в доставке")

    report = database.count_orders_by_status()

    assert report["новый"] == 1
    assert report["в доставке"] == 1
    assert report["выполнен"] == 0


def test_revenue_for_period(database):
    customer = make_customer(database)
    make_order(database, customer.id, status="выполнен", order_date="2026-06-13")
    make_order(database, customer.id, status="отменён", order_date="2026-06-13")

    revenue = database.revenue_for_period("day", reference_date=date(2026, 6, 13))

    assert revenue == 1500

