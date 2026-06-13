import sqlite3
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

try:
    from .logger_config import setup_logging
    from .models import Customer, ORDER_STATUSES, Order, OrderItem
except ImportError:
    from logger_config import setup_logging
    from models import Customer, ORDER_STATUSES, Order, OrderItem


logger = setup_logging()


def _default_sqlite_path() -> Path:
    return Path(__file__).resolve().parent / "data" / "delivery.db"


def _default_tinydb_path() -> Path:
    return Path(__file__).resolve().parent / "data" / "tinydb.json"


def _period_bounds(period: str, reference_date: Optional[date] = None) -> tuple:
    current = reference_date or date.today()
    if period == "day":
        start = current
        end = current
    elif period == "week":
        start = current - timedelta(days=current.weekday())
        end = start + timedelta(days=6)
    elif period == "month":
        start = current.replace(day=1)
        if start.month == 12:
            next_month = start.replace(year=start.year + 1, month=1)
        else:
            next_month = start.replace(month=start.month + 1)
        end = next_month - timedelta(days=1)
    else:
        raise ValueError("Период должен быть day, week или month")
    return start.isoformat(), end.isoformat()


def _normalize_items(items: Sequence[object]) -> List[OrderItem]:
    if not items:
        raise ValueError("Заказ должен содержать хотя бы один товар")

    normalized = []
    for item in items:
        if isinstance(item, OrderItem):
            normalized.append(item)
        elif isinstance(item, dict):
            normalized.append(OrderItem.from_dict(item))
        else:
            raise ValueError("Товар должен быть OrderItem или словарём")
    return normalized


class SQLiteDatabase:
    def __init__(self, db_path: Optional[object] = None) -> None:
        self.db_path = Path(db_path) if db_path else _default_sqlite_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(self.db_path))
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.create_tables()

    def create_tables(self) -> None:
        with self.connection:
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS customers (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    phone TEXT,
                    address TEXT
                )
                """
            )
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY,
                    customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE RESTRICT,
                    order_date TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('новый', 'в доставке', 'выполнен', 'отменён')),
                    total REAL NOT NULL
                )
                """
            )
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS order_items (
                    id INTEGER PRIMARY KEY,
                    order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
                    product_name TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    price REAL NOT NULL
                )
                """
            )

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "SQLiteDatabase":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    def add_customer(
        self,
        name: str,
        phone: str = "",
        address: str = "",
        customer_id: Optional[int] = None,
    ) -> Customer:
        customer = Customer(customer_id, name, phone, address)
        try:
            with self.connection:
                if customer_id is None:
                    cursor = self.connection.execute(
                        "INSERT INTO customers (name, phone, address) VALUES (?, ?, ?)",
                        (customer.name, customer.phone, customer.address),
                    )
                    customer.id = cursor.lastrowid
                else:
                    self.connection.execute(
                        "INSERT INTO customers (id, name, phone, address) VALUES (?, ?, ?, ?)",
                        (customer.id, customer.name, customer.phone, customer.address),
                    )
            logger.info("Customer created: %s", customer.id)
            return customer
        except sqlite3.IntegrityError as exc:
            logger.exception("Customer creation failed")
            raise ValueError("Не удалось создать клиента: такой id уже существует") from exc

    def get_customer(self, customer_id: int) -> Optional[Customer]:
        row = self.connection.execute(
            "SELECT id, name, phone, address FROM customers WHERE id = ?",
            (customer_id,),
        ).fetchone()
        return self._customer_from_row(row) if row else None

    def list_customers(self) -> List[Customer]:
        rows = self.connection.execute(
            "SELECT id, name, phone, address FROM customers ORDER BY id"
        ).fetchall()
        return [self._customer_from_row(row) for row in rows]

    def update_customer(
        self,
        customer_id: int,
        name: Optional[str] = None,
        phone: Optional[str] = None,
        address: Optional[str] = None,
    ) -> Customer:
        current = self.get_customer(customer_id)
        if current is None:
            raise ValueError("Клиент не найден")

        updated = Customer(
            id=customer_id,
            name=name if name is not None else current.name,
            phone=phone if phone is not None else current.phone,
            address=address if address is not None else current.address,
        )
        with self.connection:
            self.connection.execute(
                "UPDATE customers SET name = ?, phone = ?, address = ? WHERE id = ?",
                (updated.name, updated.phone, updated.address, customer_id),
            )
        logger.info("Customer updated: %s", customer_id)
        return updated

    def delete_customer(self, customer_id: int) -> None:
        orders_count = self.connection.execute(
            "SELECT COUNT(*) FROM orders WHERE customer_id = ?",
            (customer_id,),
        ).fetchone()[0]
        if orders_count:
            raise ValueError("Нельзя удалить клиента, если у него есть заказы")

        with self.connection:
            cursor = self.connection.execute(
                "DELETE FROM customers WHERE id = ?",
                (customer_id,),
            )
        if cursor.rowcount == 0:
            raise ValueError("Клиент не найден")
        logger.info("Customer deleted: %s", customer_id)

    def add_order(
        self,
        customer_id: int,
        order_date: str,
        status: str,
        items: Sequence[object],
        order_id: Optional[int] = None,
    ) -> Order:
        if self.get_customer(customer_id) is None:
            raise ValueError("Клиент заказа не найден")

        normalized_items = _normalize_items(items)
        order = Order(
            id=order_id,
            customer_id=customer_id,
            order_date=order_date,
            status=status,
            items=normalized_items,
        )

        try:
            with self.connection:
                if order_id is None:
                    cursor = self.connection.execute(
                        """
                        INSERT INTO orders (customer_id, order_date, status, total)
                        VALUES (?, ?, ?, ?)
                        """,
                        (order.customer_id, order.order_date, order.status, order.total),
                    )
                    order.id = cursor.lastrowid
                else:
                    self.connection.execute(
                        """
                        INSERT INTO orders (id, customer_id, order_date, status, total)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            order.id,
                            order.customer_id,
                            order.order_date,
                            order.status,
                            order.total,
                        ),
                    )

                for item in normalized_items:
                    self.connection.execute(
                        """
                        INSERT INTO order_items (order_id, product_name, quantity, price)
                        VALUES (?, ?, ?, ?)
                        """,
                        (order.id, item.product_name, item.quantity, item.price),
                    )
            logger.info("Order created: %s", order.id)
            return self.get_order(order.id)
        except sqlite3.IntegrityError as exc:
            logger.exception("Order creation failed")
            raise ValueError("Не удалось создать заказ: проверьте id и данные") from exc

    def get_order(self, order_id: int) -> Optional[Order]:
        row = self.connection.execute(
            """
            SELECT id, customer_id, order_date, status, total
            FROM orders WHERE id = ?
            """,
            (order_id,),
        ).fetchone()
        if row is None:
            return None
        items = self._get_order_items(order_id)
        return Order(
            id=row["id"],
            customer_id=row["customer_id"],
            order_date=row["order_date"],
            status=row["status"],
            total=row["total"],
            items=items,
        )

    def list_orders(
        self,
        status: Optional[str] = None,
        order_date: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[Order]:
        query = "SELECT id FROM orders WHERE 1 = 1"
        params = []

        if status and status != "все":
            if status not in ORDER_STATUSES:
                raise ValueError("Недопустимый статус заказа")
            query += " AND status = ?"
            params.append(status)
        if order_date:
            datetime.strptime(order_date, "%Y-%m-%d")
            query += " AND order_date = ?"
            params.append(order_date)
        if start_date:
            datetime.strptime(start_date, "%Y-%m-%d")
            query += " AND order_date >= ?"
            params.append(start_date)
        if end_date:
            datetime.strptime(end_date, "%Y-%m-%d")
            query += " AND order_date <= ?"
            params.append(end_date)

        query += " ORDER BY order_date DESC, id DESC"
        rows = self.connection.execute(query, params).fetchall()
        return [self.get_order(row["id"]) for row in rows]

    def update_order(
        self,
        order_id: int,
        customer_id: Optional[int] = None,
        order_date: Optional[str] = None,
        status: Optional[str] = None,
        items: Optional[Sequence[object]] = None,
    ) -> Order:
        current = self.get_order(order_id)
        if current is None:
            raise ValueError("Заказ не найден")

        new_customer_id = customer_id if customer_id is not None else current.customer_id
        if self.get_customer(new_customer_id) is None:
            raise ValueError("Клиент заказа не найден")

        new_items = _normalize_items(items) if items is not None else current.items
        updated = Order(
            id=order_id,
            customer_id=new_customer_id,
            order_date=order_date if order_date is not None else current.order_date,
            status=status if status is not None else current.status,
            items=new_items,
        )

        with self.connection:
            self.connection.execute(
                """
                UPDATE orders
                SET customer_id = ?, order_date = ?, status = ?, total = ?
                WHERE id = ?
                """,
                (
                    updated.customer_id,
                    updated.order_date,
                    updated.status,
                    updated.total,
                    order_id,
                ),
            )
            if items is not None:
                self.connection.execute(
                    "DELETE FROM order_items WHERE order_id = ?",
                    (order_id,),
                )
                for item in new_items:
                    self.connection.execute(
                        """
                        INSERT INTO order_items (order_id, product_name, quantity, price)
                        VALUES (?, ?, ?, ?)
                        """,
                        (order_id, item.product_name, item.quantity, item.price),
                    )
        logger.info("Order updated: %s", order_id)
        return self.get_order(order_id)

    def delete_order(self, order_id: int) -> None:
        with self.connection:
            self.connection.execute(
                "DELETE FROM order_items WHERE order_id = ?",
                (order_id,),
            )
            cursor = self.connection.execute(
                "DELETE FROM orders WHERE id = ?",
                (order_id,),
            )
        if cursor.rowcount == 0:
            raise ValueError("Заказ не найден")
        logger.info("Order deleted: %s", order_id)

    def count_orders_by_status(self) -> Dict[str, int]:
        result = {status: 0 for status in ORDER_STATUSES}
        rows = self.connection.execute(
            "SELECT status, COUNT(*) AS count FROM orders GROUP BY status"
        ).fetchall()
        for row in rows:
            result[row["status"]] = row["count"]
        return result

    def top_customers_by_total(self, limit: int = 3) -> List[Dict[str, object]]:
        rows = self.connection.execute(
            """
            SELECT c.id, c.name, SUM(o.total) AS total
            FROM customers c
            JOIN orders o ON o.customer_id = c.id
            GROUP BY c.id, c.name
            ORDER BY total DESC, c.name
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [
            {"customer_id": row["id"], "name": row["name"], "total": row["total"]}
            for row in rows
        ]

    def revenue_for_period(
        self,
        period: str,
        reference_date: Optional[date] = None,
    ) -> float:
        start_date, end_date = _period_bounds(period, reference_date)
        return self.revenue_between(start_date, end_date)

    def revenue_between(self, start_date: str, end_date: str) -> float:
        row = self.connection.execute(
            """
            SELECT COALESCE(SUM(total), 0) AS revenue
            FROM orders
            WHERE order_date >= ? AND order_date <= ? AND status != 'отменён'
            """,
            (start_date, end_date),
        ).fetchone()
        return round(float(row["revenue"]), 2)

    def report(self, period: str = "month") -> Dict[str, object]:
        return {
            "orders_by_status": self.count_orders_by_status(),
            "top_customers": self.top_customers_by_total(),
            "revenue": self.revenue_for_period(period),
        }

    def _get_order_items(self, order_id: int) -> List[OrderItem]:
        rows = self.connection.execute(
            """
            SELECT id, order_id, product_name, quantity, price
            FROM order_items
            WHERE order_id = ?
            ORDER BY id
            """,
            (order_id,),
        ).fetchall()
        return [
            OrderItem(
                id=row["id"],
                order_id=row["order_id"],
                product_name=row["product_name"],
                quantity=row["quantity"],
                price=row["price"],
            )
            for row in rows
        ]

    @staticmethod
    def _customer_from_row(row: sqlite3.Row) -> Customer:
        return Customer(
            id=row["id"],
            name=row["name"],
            phone=row["phone"] or "",
            address=row["address"] or "",
        )


class TinyDBDatabase:
    def __init__(self, db_path: Optional[object] = None) -> None:
        try:
            from tinydb import Query, TinyDB
        except ImportError as exc:
            raise ImportError("Для TinyDB установите зависимость: pip install tinydb") from exc

        self.Query = Query
        self.db_path = Path(db_path) if db_path else _default_tinydb_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db = TinyDB(str(self.db_path), encoding="utf-8", ensure_ascii=False, indent=2)
        self.customers = self.db.table("customers")
        self.orders = self.db.table("orders")

    def close(self) -> None:
        self.db.close()

    def add_customer(
        self,
        name: str,
        phone: str = "",
        address: str = "",
        customer_id: Optional[int] = None,
    ) -> Customer:
        customer_id = customer_id or self._next_id(self.customers)
        if self.get_customer(customer_id) is not None:
            raise ValueError("Не удалось создать клиента: такой id уже существует")
        customer = Customer(customer_id, name, phone, address)
        self.customers.insert(customer.to_dict())
        logger.info("TinyDB customer created: %s", customer_id)
        return customer

    def get_customer(self, customer_id: int) -> Optional[Customer]:
        row = self.customers.get(self.Query().id == customer_id)
        return Customer.from_dict(row) if row else None

    def list_customers(self) -> List[Customer]:
        return [Customer.from_dict(row) for row in sorted(self.customers.all(), key=lambda row: row["id"])]

    def update_customer(
        self,
        customer_id: int,
        name: Optional[str] = None,
        phone: Optional[str] = None,
        address: Optional[str] = None,
    ) -> Customer:
        current = self.get_customer(customer_id)
        if current is None:
            raise ValueError("Клиент не найден")
        updated = Customer(
            id=customer_id,
            name=name if name is not None else current.name,
            phone=phone if phone is not None else current.phone,
            address=address if address is not None else current.address,
        )
        self.customers.update(updated.to_dict(), self.Query().id == customer_id)
        return updated

    def delete_customer(self, customer_id: int) -> None:
        if any(order["customer_id"] == customer_id for order in self.orders.all()):
            raise ValueError("Нельзя удалить клиента, если у него есть заказы")
        removed = self.customers.remove(self.Query().id == customer_id)
        if not removed:
            raise ValueError("Клиент не найден")

    def add_order(
        self,
        customer_id: int,
        order_date: str,
        status: str,
        items: Sequence[object],
        order_id: Optional[int] = None,
    ) -> Order:
        if self.get_customer(customer_id) is None:
            raise ValueError("Клиент заказа не найден")
        order_id = order_id or self._next_id(self.orders)
        if self.get_order(order_id) is not None:
            raise ValueError("Не удалось создать заказ: такой id уже существует")

        normalized_items = self._items_with_ids(order_id, _normalize_items(items))
        order = Order(order_id, customer_id, order_date, status, items=normalized_items)
        self.orders.insert(order.to_dict())
        logger.info("TinyDB order created: %s", order_id)
        return order

    def get_order(self, order_id: int) -> Optional[Order]:
        row = self.orders.get(self.Query().id == order_id)
        return Order.from_dict(row) if row else None

    def list_orders(
        self,
        status: Optional[str] = None,
        order_date: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[Order]:
        orders = [Order.from_dict(row) for row in self.orders.all()]
        if status and status != "все":
            if status not in ORDER_STATUSES:
                raise ValueError("Недопустимый статус заказа")
            orders = [order for order in orders if order.status == status]
        if order_date:
            datetime.strptime(order_date, "%Y-%m-%d")
            orders = [order for order in orders if order.order_date == order_date]
        if start_date:
            datetime.strptime(start_date, "%Y-%m-%d")
            orders = [order for order in orders if order.order_date >= start_date]
        if end_date:
            datetime.strptime(end_date, "%Y-%m-%d")
            orders = [order for order in orders if order.order_date <= end_date]
        return sorted(orders, key=lambda order: (order.order_date, order.id), reverse=True)

    def update_order(
        self,
        order_id: int,
        customer_id: Optional[int] = None,
        order_date: Optional[str] = None,
        status: Optional[str] = None,
        items: Optional[Sequence[object]] = None,
    ) -> Order:
        current = self.get_order(order_id)
        if current is None:
            raise ValueError("Заказ не найден")
        new_customer_id = customer_id if customer_id is not None else current.customer_id
        if self.get_customer(new_customer_id) is None:
            raise ValueError("Клиент заказа не найден")
        new_items = (
            self._items_with_ids(order_id, _normalize_items(items))
            if items is not None
            else current.items
        )
        updated = Order(
            id=order_id,
            customer_id=new_customer_id,
            order_date=order_date if order_date is not None else current.order_date,
            status=status if status is not None else current.status,
            items=new_items,
        )
        self.orders.update(updated.to_dict(), self.Query().id == order_id)
        return updated

    def delete_order(self, order_id: int) -> None:
        removed = self.orders.remove(self.Query().id == order_id)
        if not removed:
            raise ValueError("Заказ не найден")

    def count_orders_by_status(self) -> Dict[str, int]:
        result = {status: 0 for status in ORDER_STATUSES}
        for order in self.list_orders():
            result[order.status] += 1
        return result

    def top_customers_by_total(self, limit: int = 3) -> List[Dict[str, object]]:
        totals = defaultdict(float)
        for order in self.list_orders():
            totals[order.customer_id] += order.total
        rows = []
        for customer_id, total in totals.items():
            customer = self.get_customer(customer_id)
            if customer:
                rows.append(
                    {"customer_id": customer.id, "name": customer.name, "total": round(total, 2)}
                )
        return sorted(rows, key=lambda row: (-row["total"], row["name"]))[:limit]

    def revenue_for_period(
        self,
        period: str,
        reference_date: Optional[date] = None,
    ) -> float:
        start_date, end_date = _period_bounds(period, reference_date)
        return self.revenue_between(start_date, end_date)

    def revenue_between(self, start_date: str, end_date: str) -> float:
        return round(
            sum(
                order.total
                for order in self.list_orders(start_date=start_date, end_date=end_date)
                if order.status != "отменён"
            ),
            2,
        )

    def report(self, period: str = "month") -> Dict[str, object]:
        return {
            "orders_by_status": self.count_orders_by_status(),
            "top_customers": self.top_customers_by_total(),
            "revenue": self.revenue_for_period(period),
        }

    @staticmethod
    def _next_id(table) -> int:
        rows = table.all()
        return max((int(row["id"]) for row in rows), default=0) + 1

    def _next_item_id(self) -> int:
        item_ids = []
        for order in self.orders.all():
            item_ids.extend(int(item["id"]) for item in order.get("items", []) if item.get("id"))
        return max(item_ids, default=0) + 1

    def _items_with_ids(self, order_id: int, items: Iterable[OrderItem]) -> List[OrderItem]:
        next_item_id = self._next_item_id()
        prepared = []
        for item in items:
            prepared.append(
                OrderItem(
                    id=item.id or next_item_id,
                    order_id=order_id,
                    product_name=item.product_name,
                    quantity=item.quantity,
                    price=item.price,
                )
            )
            next_item_id += 1
        return prepared

