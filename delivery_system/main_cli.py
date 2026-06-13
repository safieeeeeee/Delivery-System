import argparse
from datetime import date
from pathlib import Path

try:
    from .data_export import export_orders, import_orders
    from .database import SQLiteDatabase
    from .logger_config import setup_logging
    from .models import ORDER_STATUSES, OrderItem
except ImportError:
    from data_export import export_orders, import_orders
    from database import SQLiteDatabase
    from logger_config import setup_logging
    from models import ORDER_STATUSES, OrderItem


logger = setup_logging()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Учёт заказов компании 'Быстрая доставка'")
    parser.add_argument(
        "--db",
        default=str(Path(__file__).resolve().parent / "data" / "delivery.db"),
        help="Путь к SQLite-файлу",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    report_parser = subparsers.add_parser("report", help="Показать отчёт")
    report_parser.add_argument("--period", choices=("day", "week", "month"), default="month")

    export_parser = subparsers.add_parser("export", help="Экспорт заказов")
    export_parser.add_argument("--file", required=True, help="Файл .json или .xml")

    import_parser = subparsers.add_parser("import", help="Импорт заказов")
    import_parser.add_argument("--file", required=True, help="Файл .json или .xml")

    customer_parser = subparsers.add_parser("customer", help="Управление клиентами")
    customer_subparsers = customer_parser.add_subparsers(dest="action", required=True)
    customer_add = customer_subparsers.add_parser("add", help="Добавить клиента")
    customer_add.add_argument("--name", required=True)
    customer_add.add_argument("--phone", default="")
    customer_add.add_argument("--address", default="")
    customer_subparsers.add_parser("list", help="Список клиентов")
    customer_update = customer_subparsers.add_parser("update", help="Изменить клиента")
    customer_update.add_argument("--id", type=int, required=True)
    customer_update.add_argument("--name")
    customer_update.add_argument("--phone")
    customer_update.add_argument("--address")
    customer_delete = customer_subparsers.add_parser("delete", help="Удалить клиента")
    customer_delete.add_argument("--id", type=int, required=True)

    order_parser = subparsers.add_parser("order", help="Управление заказами")
    order_subparsers = order_parser.add_subparsers(dest="action", required=True)
    order_add = order_subparsers.add_parser("add", help="Добавить заказ")
    order_add.add_argument("--customer-id", type=int, required=True)
    order_add.add_argument("--date", default=date.today().isoformat())
    order_add.add_argument("--status", choices=ORDER_STATUSES, default="новый")
    order_add.add_argument(
        "--item",
        action="append",
        required=True,
        help="Товар в формате 'Название;Количество;Цена'. Можно передать несколько раз",
    )
    order_list = order_subparsers.add_parser("list", help="Список заказов")
    order_list.add_argument("--status", choices=("все",) + ORDER_STATUSES, default="все")
    order_list.add_argument("--date")
    order_update = order_subparsers.add_parser("update", help="Изменить заказ")
    order_update.add_argument("--id", type=int, required=True)
    order_update.add_argument("--customer-id", type=int)
    order_update.add_argument("--date")
    order_update.add_argument("--status", choices=ORDER_STATUSES)
    order_update.add_argument("--item", action="append")
    order_delete = order_subparsers.add_parser("delete", help="Удалить заказ")
    order_delete.add_argument("--id", type=int, required=True)

    return parser


def parse_items(raw_items) -> list:
    items = []
    for raw_item in raw_items:
        parts = [part.strip() for part in raw_item.split(";")]
        if len(parts) != 3:
            raise ValueError("Товар должен быть в формате 'Название;Количество;Цена'")
        items.append(OrderItem(product_name=parts[0], quantity=parts[1], price=parts[2]))
    return items


def print_report(database: SQLiteDatabase, period: str) -> None:
    report = database.report(period)
    print("Заказы по статусам:")
    for status, count in report["orders_by_status"].items():
        print(f"  {status}: {count}")

    print("\nТоп-3 клиента по сумме заказов:")
    if report["top_customers"]:
        for row in report["top_customers"]:
            print(f"  {row['name']} (id={row['customer_id']}): {row['total']:.2f}")
    else:
        print("  данных нет")

    print(f"\nВыручка за период '{period}': {report['revenue']:.2f}")


def print_customers(database: SQLiteDatabase) -> None:
    customers = database.list_customers()
    if not customers:
        print("Клиентов нет")
        return
    for customer in customers:
        print(f"{customer.id}: {customer.name} | {customer.phone} | {customer.address}")


def print_orders(database: SQLiteDatabase, status: str, order_date: str) -> None:
    orders = database.list_orders(status=status, order_date=order_date)
    if not orders:
        print("Заказов нет")
        return
    for order in orders:
        customer = database.get_customer(order.customer_id)
        customer_name = customer.name if customer else f"id={order.customer_id}"
        print(
            f"{order.id}: {order.order_date} | {customer_name} | "
            f"{order.status} | {order.total:.2f}"
        )
        for item in order.items:
            print(f"  - {item.product_name}: {item.quantity} x {item.price:.2f}")


def handle_args(args: argparse.Namespace) -> int:
    database = SQLiteDatabase(args.db)
    try:
        if args.command == "report":
            print_report(database, args.period)
        elif args.command == "export":
            count = export_orders(database, args.file)
            print(f"Экспортировано заказов: {count}")
        elif args.command == "import":
            count = import_orders(database, args.file)
            print(f"Импортировано заказов: {count}")
        elif args.command == "customer":
            handle_customer_command(database, args)
        elif args.command == "order":
            handle_order_command(database, args)
        else:
            raise ValueError("Неизвестная команда")
        return 0
    finally:
        database.close()


def handle_customer_command(database: SQLiteDatabase, args: argparse.Namespace) -> None:
    if args.action == "add":
        customer = database.add_customer(args.name, args.phone, args.address)
        print(f"Клиент создан: id={customer.id}")
    elif args.action == "list":
        print_customers(database)
    elif args.action == "update":
        customer = database.update_customer(args.id, args.name, args.phone, args.address)
        print(f"Клиент обновлён: {customer.id}")
    elif args.action == "delete":
        database.delete_customer(args.id)
        print("Клиент удалён")


def handle_order_command(database: SQLiteDatabase, args: argparse.Namespace) -> None:
    if args.action == "add":
        order = database.add_order(
            customer_id=args.customer_id,
            order_date=args.date,
            status=args.status,
            items=parse_items(args.item),
        )
        print(f"Заказ создан: id={order.id}, сумма={order.total:.2f}")
    elif args.action == "list":
        print_orders(database, args.status, args.date)
    elif args.action == "update":
        items = parse_items(args.item) if args.item else None
        order = database.update_order(
            order_id=args.id,
            customer_id=args.customer_id,
            order_date=args.date,
            status=args.status,
            items=items,
        )
        print(f"Заказ обновлён: id={order.id}, сумма={order.total:.2f}")
    elif args.action == "delete":
        database.delete_order(args.id)
        print("Заказ удалён")


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return handle_args(args)
    except Exception as exc:
        logger.exception("CLI command failed")
        print(f"Ошибка: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

