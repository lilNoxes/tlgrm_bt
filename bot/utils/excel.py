import io
from typing import Any, Dict, List
import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter


def create_students_excel(students_data: List[Dict[str, Any]]) -> io.BytesIO:
    """Формирует красиво оформленный Excel-файл со списком оплативших учеников в памяти."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Оплатившие ученики"

    # Заголовки таблицы
    headers = [
        "№ Заказа",
        "Дата оплаты",
        "Telegram ID",
        "Username",
        "ФИО ученика",
        "Телефон",
        "Email",
        "Тариф",
        "Сумма (руб.)",
        "ID транзакции ЮKassa"
    ]

    ws.append(headers)

    # Стили для шапки
    header_fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
    header_font = Font(name="Arial", size=11, bold=True, color="FFFFFF")
    center_align = Alignment(horizontal="center", vertical="center")
    thin_border = Border(
        left=Side(style="thin", color="D9D9D9"),
        right=Side(style="thin", color="D9D9D9"),
        top=Side(style="thin", color="D9D9D9"),
        bottom=Side(style="thin", color="D9D9D9")
    )

    for col_num, _ in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_num)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = center_align

    # Заполнение строк
    for row_idx, item in enumerate(students_data, start=2):
        row_values = [
            item.get("order_id"),
            item.get("paid_at"),
            item.get("telegram_id"),
            item.get("username"),
            item.get("full_name"),
            item.get("phone"),
            item.get("email"),
            item.get("tariff_title"),
            item.get("amount_rub"),
            item.get("provider_charge_id")
        ]
        ws.append(row_values)

        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            cell.font = Font(name="Arial", size=10)
            cell.border = thin_border
            if col_idx in (1, 2, 3, 9):
                cell.alignment = center_align
            else:
                cell.alignment = Alignment(vertical="center")

    # Автоматическая ширина колонок
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            val_str = str(cell.value or "")
            if len(val_str) > max_len:
                max_len = len(val_str)
        ws.column_dimensions[col_letter].width = max(max_len + 4, 12)

    # Сохранение в BytesIO
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer
