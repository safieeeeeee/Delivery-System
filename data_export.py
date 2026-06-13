import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Iterable, List

try:
    from .logger_config import setup_logging
    from .models import Customer, ORDER_STATUSES, OrderItem
except ImportError:
    from logger_config import setup_logging
    from models import Customer, ORDER_STATUSES, OrderItem


logger = setup_logging()


def export_orders(database, file_path: object) -> int:
    path = Path(file_path)
    if path.suffix.lower() == ".json":
        return export_orders_json(database, path)
    if path.suffix.lower() == ".xml":
        return export_orders_xml(database, path)
    raise ValueError("Формат экспорта должен быть .json или .xml")


def import_orders(database, file_path: object) -> int:
    path = Path(file_path)
    if path.suffix.lower() == ".json":
        return import_orders_json(database, path)
    if path.suffix.lower() == ".xml":
        return import_orders_xml(database, path)
    raise ValueError("Формат импорта должен быть .json или .xml")


def export_orders_json(database, file_path: object) -> int:
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    orders = [_order_to_payload(database, order) for order in database.list_orders()]
    with path.open("w", encoding="utf-8") as file:
        json.dump({"orders": orders}, file, ensure_ascii=False, indent=2)
    logger.info("Exported %s orders to JSON: %s", len(orders), path)
    return len(orders)


def import_orders_json(database, file_path: object) -> int:
    path = Path(file_path)
    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
        orders = data.get("orders") if isinstance(data, dict) else data
        if not isinstance(orders, list):
            raise ValueError("JSON должен содержать список заказов или объект {'orders': [...]}")
        count = _import_payloads(database, orders)
        logger.info("Imported %s orders from JSON: %s", count, path)
        return count
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        logger.exception("JSON import failed")
        raise ValueError(f"Ошибка импорта JSON: {exc}") from exc


def export_orders_xml(database, file_path: object) -> int:
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    root = ET.Element("orders")
    orders = database.list_orders()

    for order in orders:
        order_element = ET.SubElement(
            root,
            "order",
            {
                "id": str(order.id),
                "customer_id": str(order.customer_id),
                "order_date": order.order_date,
                "status": order.status,
                "total": str(order.total),
            },
        )
        customer = database.get_customer(order.customer_id)
        if customer:
            ET.SubElement(
                order_element,
                "customer",
                {
                    "id": str(customer.id),
                    "name": customer.name,
                    "phone": customer.phone,
                    "address": customer.address,
                },
            )
        items_element = ET.SubElement(order_element, "items")
        for item in order.items:
            ET.SubElement(
                items_element,
                "item",
                {
                    "id": str(item.id or ""),
                    "order_id": str(order.id),
                    "product_name": item.product_name,
                    "quantity": str(item.quantity),
                    "price": str(item.price),
                },
            )

    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    tree.write(path, encoding="utf-8", xml_declaration=True)
    logger.info("Exported %s orders to XML: %s", len(orders), path)
    return len(orders)


def import_orders_xml(database, file_path: object) -> int:
    path = Path(file_path)
    try:
        tree = ET.parse(path)
        root = tree.getroot()
        if root.tag != "orders":
            raise ValueError("Корневой XML-элемент должен называться orders")
        payloads = [_xml_order_to_payload(element) for element in root.findall("order")]
        count = _import_payloads(database, payloads)
        logger.info("Imported %s orders from XML: %s", count, path)
        return count
    except (OSError, ET.ParseError, ValueError) as exc:
        logger.exception("XML import failed")
        raise ValueError(f"Ошибка импорта XML: {exc}") from exc


def _order_to_payload(database, order) -> Dict[str, object]:
    customer = database.get_customer(order.customer_id)
    return order.to_dict(customer=customer)


def _import_payloads(database, payloads: Iterable[Dict[str, object]]) -> int:
    count = 0
    for index, payload in enumerate(payloads, start=1):
        try:
            _import_order_payload(database, payload)
            count += 1
        except ValueError as exc:
            raise ValueError(f"Заказ #{index}: {exc}") from exc
    return count


def _import_order_payload(database, payload: Dict[str, object]) -> None:
    _validate_required(payload, ("order_date", "status", "items"))
    status = str(payload["status"])
    if status not in ORDER_STATUSES:
        raise ValueError(f"недопустимый статус '{status}'")

    customer_id = _ensure_customer(database, payload)
    items = _validate_items(payload["items"])
    order_id = _optional_int(payload.get("id"), "id")

    if order_id and database.get_order(order_id):
        database.update_order(
            order_id=order_id,
            customer_id=customer_id,
            order_date=str(payload["order_date"]),
            status=status,
            items=items,
        )
    else:
        database.add_order(
            customer_id=customer_id,
            order_date=str(payload["order_date"]),
            status=status,
            items=items,
            order_id=order_id,
        )


def _ensure_customer(database, payload: Dict[str, object]) -> int:
    customer_payload = payload.get("customer")
    customer_id = _optional_int(payload.get("customer_id"), "customer_id")

    if customer_id and database.get_customer(customer_id):
        return customer_id

    if isinstance(customer_payload, dict):
        preferred_id = customer_id or _optional_int(customer_payload.get("id"), "customer.id")
        customer = Customer.from_dict(
            {
                "id": preferred_id,
                "name": customer_payload.get("name", ""),
                "phone": customer_payload.get("phone", ""),
                "address": customer_payload.get("address", ""),
            }
        )
        created = database.add_customer(
            customer.name,
            customer.phone,
            customer.address,
            customer_id=customer.id,
        )
        return created.id

    raise ValueError("клиент не найден, а данные клиента не переданы")


def _validate_items(items: object) -> List[OrderItem]:
    if not isinstance(items, list) or not items:
        raise ValueError("поле items должно быть непустым списком")

    validated = []
    for item_index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"товар #{item_index} должен быть объектом")
        _validate_required(item, ("product_name", "quantity", "price"))
        try:
            validated.append(
                OrderItem(
                    id=_optional_int(item.get("id"), "item.id"),
                    order_id=_optional_int(item.get("order_id"), "item.order_id"),
                    product_name=str(item["product_name"]),
                    quantity=item["quantity"],
                    price=item["price"],
                )
            )
        except ValueError as exc:
            raise ValueError(f"товар #{item_index}: {exc}") from exc
    return validated


def _validate_required(payload: Dict[str, object], fields: Iterable[str]) -> None:
    missing = [field for field in fields if field not in payload or payload[field] in (None, "")]
    if missing:
        raise ValueError("отсутствуют обязательные поля: " + ", ".join(missing))


def _optional_int(value: object, field_name: str) -> object:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"поле {field_name} должно быть целым числом") from exc


def _xml_order_to_payload(order_element: ET.Element) -> Dict[str, object]:
    payload = {
        "id": order_element.get("id"),
        "customer_id": order_element.get("customer_id"),
        "order_date": order_element.get("order_date"),
        "status": order_element.get("status"),
        "total": order_element.get("total"),
        "items": [],
    }

    customer_element = order_element.find("customer")
    if customer_element is not None:
        payload["customer"] = {
            "id": customer_element.get("id"),
            "name": customer_element.get("name"),
            "phone": customer_element.get("phone", ""),
            "address": customer_element.get("address", ""),
        }

    items_element = order_element.find("items")
    if items_element is not None:
        payload["items"] = [
            {
                "id": item.get("id"),
                "order_id": item.get("order_id"),
                "product_name": item.get("product_name"),
                "quantity": item.get("quantity"),
                "price": item.get("price"),
            }
            for item in items_element.findall("item")
        ]

    return payload

