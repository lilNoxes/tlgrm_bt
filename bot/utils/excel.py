import io
from typing import Any, Dict, List
import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter


def _style_sheet(ws, headers: List[str], rows: List[List[Any]], header_color: str = "1F4E79") -> None:
    """Применяет стили, оформление и автоширину к листу Excel."""
    ws.append(headers)

    header_fill = PatternFill(start_color=header_color, end_color=header_color, fill_type="solid")
    header_font = Font(name="Arial", size=11, bold=True, color="FFFFFF")
    center_align = Alignment(horizontal="center", vertical="center")
    thin_border = Border(
        left=Side(style="thin", color="D9D9D9"),
        right=Side(style="thin", color="D9D9D9"),
        top=Side(style="thin", color="D9D9D9"),
        bottom=Side(style="thin", color="D9D9D9")
    )

    # Оформление шапки
    for col_num in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_num)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = center_align

    # Заполнение строк
    for row_idx, row_values in enumerate(rows, start=2):
        ws.append(row_values)
        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            cell.font = Font(name="Arial", size=10)
            cell.border = thin_border
            # Центрируем ID, даты и числовые колонки
            if col_idx in (1, 2, 3):
                cell.alignment = center_align
            else:
                cell.alignment = Alignment(vertical="center")

    # Автоподбор ширины колонок
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            val_str = str(cell.value or "")
            if len(val_str) > max_len:
                max_len = len(val_str)
        ws.column_dimensions[col_letter].width = max(max_len + 4, 12)


def create_full_report_excel(
    paid_students: List[Dict[str, Any]],
    unpaid_leads: List[Dict[str, Any]],
    all_users: List[Dict[str, Any]]
) -> io.BytesIO:
    """Формирует сводный Excel-файл со всеми категориями (на 3 отдельных вкладках)."""
    wb = openpyxl.Workbook()

    # Вкладка 1: Оплатившие ученики
    ws_paid = wb.active
    ws_paid.title = "Оплатившие курс"
    paid_headers = [
        "№ Заказа", "Дата оплаты", "Telegram ID", "Username",
        "ФИО ученика", "Телефон", "Email", "Тариф", "Сумма (руб.)", "ID ЮKassa"
    ]
    paid_rows = [
        [
            item.get("order_id"), item.get("paid_at"), item.get("telegram_id"),
            item.get("username"), item.get("full_name"), item.get("phone"),
            item.get("email"), item.get("tariff_title"), item.get("amount_rub"),
            item.get("provider_charge_id")
        ]
        for item in paid_students
    ]
    _style_sheet(ws_paid, paid_headers, paid_rows, header_color="1F4E79")

    # Вкладка 2: Лиды (оставили контакты, но не оплатили)
    ws_unpaid = wb.create_sheet(title="Лиды без оплаты")
    unpaid_headers = [
        "Telegram ID", "Username", "ФИО", "Телефон", "Email", "Дата регистрации"
    ]
    unpaid_rows = [
        [
            item.get("telegram_id"), item.get("username"), item.get("full_name"),
            item.get("phone"), item.get("email"), item.get("registered_at")
        ]
        for item in unpaid_leads
    ]
    _style_sheet(ws_unpaid, unpaid_headers, unpaid_rows, header_color="C65911")

    # Вкладка 3: Все пользователи бота (включая новых)
    ws_all = wb.create_sheet(title="Все пользователи")
    all_headers = [
        "Telegram ID", "Username", "ФИО", "Телефон", "Email", "Статус", "Дата первого входа"
    ]
    all_rows = [
        [
            item.get("telegram_id"), item.get("username"), item.get("full_name"),
            item.get("phone"), item.get("email"), item.get("status"), item.get("first_seen")
        ]
        for item in all_users
    ]
    _style_sheet(ws_all, all_headers, all_rows, header_color="385723")

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer


def create_paid_students_excel(students_data: List[Dict[str, Any]]) -> io.BytesIO:
    """Отдельный файл: Только оплатившие ученики."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Оплатившие курс"
    headers = [
        "№ Заказа", "Дата оплаты", "Telegram ID", "Username",
        "ФИО ученика", "Телефон", "Email", "Тариф", "Сумма (руб.)", "ID ЮKassa"
    ]
    rows = [
        [
            item.get("order_id"), item.get("paid_at"), item.get("telegram_id"),
            item.get("username"), item.get("full_name"), item.get("phone"),
            item.get("email"), item.get("tariff_title"), item.get("amount_rub"),
            item.get("provider_charge_id")
        ]
        for item in students_data
    ]
    _style_sheet(ws, headers, rows, header_color="1F4E79")
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer


def create_unpaid_leads_excel(leads_data: List[Dict[str, Any]]) -> io.BytesIO:
    """Отдельный файл: Лиды, заполнившие контакты без оплаты."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Контакты без оплаты"
    headers = [
        "Telegram ID", "Username", "ФИО", "Телефон", "Email", "Дата регистрации"
    ]
    rows = [
        [
            item.get("telegram_id"), item.get("username"), item.get("full_name"),
            item.get("phone"), item.get("email"), item.get("registered_at")
        ]
        for item in leads_data
    ]
    _style_sheet(ws, headers, rows, header_color="C65911")
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer


def create_all_users_excel(users_data: List[Dict[str, Any]]) -> io.BytesIO:
    """Отдельный файл: Все пользователи бота (включая новых)."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Все пользователи"
    headers = [
        "Telegram ID", "Username", "ФИО", "Телефон", "Email", "Статус", "Дата первого входа"
    ]
    rows = [
        [
            item.get("telegram_id"), item.get("username"), item.get("full_name"),
            item.get("phone"), item.get("email"), item.get("status"), item.get("first_seen")
        ]
        for item in users_data
    ]
    _style_sheet(ws, headers, rows, header_color="385723")
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer


# Совместимость со старым вызовом
create_students_excel = create_paid_students_excel
