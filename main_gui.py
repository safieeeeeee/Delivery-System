import tkinter as tk
from datetime import date
from tkinter import filedialog, messagebox, ttk

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


class DeliveryGUI:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Быстрая доставка")
        self.root.geometry("980x560")
        self.database = SQLiteDatabase()
        self.status_filter = tk.StringVar(value="все")
        self.export_format = tk.StringVar(value="json")
        self._build_widgets()
        self.refresh_orders()
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def _build_widgets(self) -> None:
        filter_frame = ttk.Frame(self.root, padding=8)
        filter_frame.pack(fill=tk.X)

        ttk.Label(filter_frame, text="Статус:").pack(side=tk.LEFT)
        status_box = ttk.Combobox(
            filter_frame,
            textvariable=self.status_filter,
            values=("все",) + ORDER_STATUSES,
            state="readonly",
            width=16,
        )
        status_box.pack(side=tk.LEFT, padx=6)
        ttk.Button(filter_frame, text="Применить", command=self.refresh_orders).pack(side=tk.LEFT)

        ttk.Label(filter_frame, text="Формат:").pack(side=tk.RIGHT, padx=(12, 4))
        ttk.Combobox(
            filter_frame,
            textvariable=self.export_format,
            values=("json", "xml"),
            state="readonly",
            width=7,
        ).pack(side=tk.RIGHT)

        columns = ("id", "date", "customer", "status", "total")
        self.tree = ttk.Treeview(self.root, columns=columns, show="headings", height=18)
        headings = {
            "id": "ID",
            "date": "Дата",
            "customer": "Клиент",
            "status": "Статус",
            "total": "Сумма",
        }
        widths = {"id": 60, "date": 120, "customer": 300, "status": 140, "total": 120}
        for column in columns:
            self.tree.heading(column, text=headings[column])
            self.tree.column(column, width=widths[column], anchor=tk.W)
        self.tree.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        buttons = ttk.Frame(self.root, padding=8)
        buttons.pack(fill=tk.X)
        ttk.Button(buttons, text="Добавить", command=self.add_order).pack(side=tk.LEFT, padx=3)
        ttk.Button(buttons, text="Редактировать", command=self.edit_order).pack(side=tk.LEFT, padx=3)
        ttk.Button(buttons, text="Удалить", command=self.delete_order).pack(side=tk.LEFT, padx=3)
        ttk.Button(buttons, text="Показать отчёт", command=self.show_report).pack(side=tk.LEFT, padx=3)
        ttk.Button(buttons, text="Клиенты", command=self.open_customers_window).pack(side=tk.LEFT, padx=3)
        ttk.Button(buttons, text="Экспорт", command=self.export_data).pack(side=tk.RIGHT, padx=3)
        ttk.Button(buttons, text="Импорт", command=self.import_data).pack(side=tk.RIGHT, padx=3)

    def refresh_orders(self) -> None:
        for row in self.tree.get_children():
            self.tree.delete(row)
        try:
            orders = self.database.list_orders(status=self.status_filter.get())
            for order in orders:
                customer = self.database.get_customer(order.customer_id)
                customer_name = customer.name if customer else f"id={order.customer_id}"
                self.tree.insert(
                    "",
                    tk.END,
                    iid=str(order.id),
                    values=(
                        order.id,
                        order.order_date,
                        customer_name,
                        order.status,
                        f"{order.total:.2f}",
                    ),
                )
        except Exception as exc:
            logger.exception("Failed to refresh orders")
            messagebox.showerror("Ошибка", str(exc))

    def selected_order_id(self) -> int:
        selected = self.tree.selection()
        if not selected:
            raise ValueError("Выберите заказ")
        return int(selected[0])

    def add_order(self) -> None:
        self.open_order_form()

    def edit_order(self) -> None:
        try:
            self.open_order_form(self.selected_order_id())
        except ValueError as exc:
            messagebox.showwarning("Внимание", str(exc))

    def delete_order(self) -> None:
        try:
            order_id = self.selected_order_id()
            if messagebox.askyesno("Удаление", "Удалить выбранный заказ?"):
                self.database.delete_order(order_id)
                self.refresh_orders()
        except Exception as exc:
            logger.exception("Failed to delete order")
            messagebox.showerror("Ошибка", str(exc))

    def open_order_form(self, order_id=None) -> None:
        customers = self.database.list_customers()
        if not customers:
            messagebox.showinfo("Клиенты", "Сначала добавьте клиента")
            self.open_customers_window()
            return

        order = self.database.get_order(order_id) if order_id else None
        window = tk.Toplevel(self.root)
        window.title("Заказ")
        window.geometry("520x430")
        window.transient(self.root)
        window.grab_set()

        customer_values = [f"{customer.id} - {customer.name}" for customer in customers]
        default_customer = (
            f"{order.customer_id} - {self.database.get_customer(order.customer_id).name}"
            if order
            else customer_values[0]
        )
        customer_var = tk.StringVar(value=default_customer)
        date_var = tk.StringVar(value=order.order_date if order else date.today().isoformat())
        status_var = tk.StringVar(value=order.status if order else "новый")

        form = ttk.Frame(window, padding=10)
        form.pack(fill=tk.BOTH, expand=True)
        ttk.Label(form, text="Клиент").pack(anchor=tk.W)
        ttk.Combobox(form, textvariable=customer_var, values=customer_values, state="readonly").pack(
            fill=tk.X, pady=4
        )
        ttk.Label(form, text="Дата YYYY-MM-DD").pack(anchor=tk.W)
        ttk.Entry(form, textvariable=date_var).pack(fill=tk.X, pady=4)
        ttk.Label(form, text="Статус").pack(anchor=tk.W)
        ttk.Combobox(form, textvariable=status_var, values=ORDER_STATUSES, state="readonly").pack(
            fill=tk.X, pady=4
        )
        ttk.Label(form, text="Товары: название;количество;цена").pack(anchor=tk.W)
        items_text = tk.Text(form, height=9)
        items_text.pack(fill=tk.BOTH, expand=True, pady=4)
        if order:
            items_text.insert(
                tk.END,
                "\n".join(
                    f"{item.product_name};{item.quantity};{item.price}" for item in order.items
                ),
            )
        else:
            items_text.insert(tk.END, "Пицца;2;750")

        def save() -> None:
            try:
                customer_id = int(customer_var.get().split(" - ", 1)[0])
                items = parse_items_text(items_text.get("1.0", tk.END))
                if order:
                    self.database.update_order(
                        order.id,
                        customer_id=customer_id,
                        order_date=date_var.get(),
                        status=status_var.get(),
                        items=items,
                    )
                else:
                    self.database.add_order(
                        customer_id=customer_id,
                        order_date=date_var.get(),
                        status=status_var.get(),
                        items=items,
                    )
                window.destroy()
                self.refresh_orders()
            except Exception as exc:
                logger.exception("Failed to save order")
                messagebox.showerror("Ошибка", str(exc))

        ttk.Button(form, text="Сохранить", command=save).pack(anchor=tk.E, pady=8)

    def open_customers_window(self) -> None:
        window = tk.Toplevel(self.root)
        window.title("Клиенты")
        window.geometry("700x420")
        window.transient(self.root)

        tree = ttk.Treeview(window, columns=("id", "name", "phone", "address"), show="headings")
        for column, title in (
            ("id", "ID"),
            ("name", "Имя"),
            ("phone", "Телефон"),
            ("address", "Адрес"),
        ):
            tree.heading(column, text=title)
            tree.column(column, width=120 if column != "address" else 260)
        tree.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        def refresh_customers() -> None:
            for row in tree.get_children():
                tree.delete(row)
            for customer in self.database.list_customers():
                tree.insert(
                    "",
                    tk.END,
                    iid=str(customer.id),
                    values=(customer.id, customer.name, customer.phone, customer.address),
                )

        def selected_customer_id() -> int:
            selected = tree.selection()
            if not selected:
                raise ValueError("Выберите клиента")
            return int(selected[0])

        def open_customer_form(customer_id=None) -> None:
            customer = self.database.get_customer(customer_id) if customer_id else None
            dialog = tk.Toplevel(window)
            dialog.title("Клиент")
            dialog.geometry("420x240")
            dialog.transient(window)
            dialog.grab_set()
            name_var = tk.StringVar(value=customer.name if customer else "")
            phone_var = tk.StringVar(value=customer.phone if customer else "")
            address_var = tk.StringVar(value=customer.address if customer else "")
            frame = ttk.Frame(dialog, padding=10)
            frame.pack(fill=tk.BOTH, expand=True)
            for label, variable in (
                ("Имя", name_var),
                ("Телефон", phone_var),
                ("Адрес", address_var),
            ):
                ttk.Label(frame, text=label).pack(anchor=tk.W)
                ttk.Entry(frame, textvariable=variable).pack(fill=tk.X, pady=4)

            def save_customer() -> None:
                try:
                    if customer:
                        self.database.update_customer(
                            customer.id,
                            name=name_var.get(),
                            phone=phone_var.get(),
                            address=address_var.get(),
                        )
                    else:
                        self.database.add_customer(
                            name_var.get(),
                            phone_var.get(),
                            address_var.get(),
                        )
                    dialog.destroy()
                    refresh_customers()
                    self.refresh_orders()
                except Exception as exc:
                    logger.exception("Failed to save customer")
                    messagebox.showerror("Ошибка", str(exc))

            ttk.Button(frame, text="Сохранить", command=save_customer).pack(anchor=tk.E, pady=8)

        def delete_customer() -> None:
            try:
                customer_id = selected_customer_id()
                if messagebox.askyesno("Удаление", "Удалить выбранного клиента?"):
                    self.database.delete_customer(customer_id)
                    refresh_customers()
            except Exception as exc:
                logger.exception("Failed to delete customer")
                messagebox.showerror("Ошибка", str(exc))

        buttons = ttk.Frame(window, padding=8)
        buttons.pack(fill=tk.X)
        ttk.Button(buttons, text="Добавить", command=open_customer_form).pack(side=tk.LEFT, padx=3)
        ttk.Button(
            buttons,
            text="Редактировать",
            command=lambda: open_customer_form(selected_customer_id()),
        ).pack(side=tk.LEFT, padx=3)
        ttk.Button(buttons, text="Удалить", command=delete_customer).pack(side=tk.LEFT, padx=3)
        refresh_customers()

    def show_report(self) -> None:
        report = self.database.report("month")
        window = tk.Toplevel(self.root)
        window.title("Отчёт")
        window.geometry("430x360")
        text = tk.Text(window, wrap=tk.WORD)
        text.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        text.insert(tk.END, "Количество заказов по статусам:\n")
        for status, count in report["orders_by_status"].items():
            text.insert(tk.END, f"  {status}: {count}\n")
        text.insert(tk.END, "\nТоп-3 клиента по сумме заказов:\n")
        if report["top_customers"]:
            for row in report["top_customers"]:
                text.insert(tk.END, f"  {row['name']}: {row['total']:.2f}\n")
        else:
            text.insert(tk.END, "  данных нет\n")
        text.insert(tk.END, f"\nВыручка за день: {self.database.revenue_for_period('day'):.2f}\n")
        text.insert(tk.END, f"Выручка за неделю: {self.database.revenue_for_period('week'):.2f}\n")
        text.insert(tk.END, f"Выручка за месяц: {report['revenue']:.2f}\n")
        text.configure(state=tk.DISABLED)

    def export_data(self) -> None:
        extension = self.export_format.get()
        file_path = filedialog.asksaveasfilename(
            defaultextension=f".{extension}",
            filetypes=((extension.upper(), f"*.{extension}"),),
        )
        if not file_path:
            return
        try:
            count = export_orders(self.database, file_path)
            messagebox.showinfo("Экспорт", f"Экспортировано заказов: {count}")
        except Exception as exc:
            logger.exception("Export failed")
            messagebox.showerror("Ошибка", str(exc))

    def import_data(self) -> None:
        file_path = filedialog.askopenfilename(
            filetypes=(("JSON/XML", "*.json *.xml"), ("JSON", "*.json"), ("XML", "*.xml"))
        )
        if not file_path:
            return
        try:
            count = import_orders(self.database, file_path)
            self.refresh_orders()
            messagebox.showinfo("Импорт", f"Импортировано заказов: {count}")
        except Exception as exc:
            logger.exception("Import failed")
            messagebox.showerror("Ошибка", str(exc))

    def close(self) -> None:
        self.database.close()
        self.root.destroy()


def parse_items_text(raw_text: str) -> list:
    items = []
    for line in raw_text.splitlines():
        if not line.strip():
            continue
        parts = [part.strip() for part in line.split(";")]
        if len(parts) != 3:
            raise ValueError("Каждый товар должен быть в формате 'Название;Количество;Цена'")
        items.append(OrderItem(product_name=parts[0], quantity=parts[1], price=parts[2]))
    if not items:
        raise ValueError("Добавьте хотя бы один товар")
    return items


def main() -> None:
    root = tk.Tk()
    DeliveryGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()

