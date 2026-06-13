import json

from delivery_system.data_export import (
    export_orders_json,
    export_orders_xml,
    import_orders_json,
    import_orders_xml,
)
from delivery_system.database import SQLiteDatabase
from delivery_system.models import OrderItem


def seed_database(database):
    customer = database.add_customer("Иван", "+79990000000", "Москва")
    order = database.add_order(
        customer_id=customer.id,
        order_date="2026-06-13",
        status="новый",
        items=[OrderItem(product_name="Пицца", quantity=2, price=750)],
    )
    return customer, order


def test_export_json(tmp_path):
    database = SQLiteDatabase(tmp_path / "source.db")
    try:
        seed_database(database)
        export_file = tmp_path / "orders.json"

        count = export_orders_json(database, export_file)

        data = json.loads(export_file.read_text(encoding="utf-8"))
        assert count == 1
        assert data["orders"][0]["customer"]["name"] == "Иван"
        assert data["orders"][0]["items"][0]["product_name"] == "Пицца"
    finally:
        database.close()


def test_import_json(tmp_path):
    source = SQLiteDatabase(tmp_path / "source.db")
    target = SQLiteDatabase(tmp_path / "target.db")
    try:
        seed_database(source)
        export_file = tmp_path / "orders.json"
        export_orders_json(source, export_file)

        count = import_orders_json(target, export_file)

        assert count == 1
        assert len(target.list_customers()) == 1
        assert target.list_orders()[0].total == 1500
    finally:
        source.close()
        target.close()


def test_export_xml(tmp_path):
    database = SQLiteDatabase(tmp_path / "source.db")
    try:
        seed_database(database)
        export_file = tmp_path / "orders.xml"

        count = export_orders_xml(database, export_file)

        content = export_file.read_text(encoding="utf-8")
        assert count == 1
        assert "<orders>" in content
        assert "Пицца" in content
    finally:
        database.close()


def test_import_xml(tmp_path):
    source = SQLiteDatabase(tmp_path / "source.db")
    target = SQLiteDatabase(tmp_path / "target.db")
    try:
        seed_database(source)
        export_file = tmp_path / "orders.xml"
        export_orders_xml(source, export_file)

        count = import_orders_xml(target, export_file)

        assert count == 1
        assert len(target.list_customers()) == 1
        assert target.list_orders()[0].items[0].product_name == "Пицца"
    finally:
        source.close()
        target.close()

