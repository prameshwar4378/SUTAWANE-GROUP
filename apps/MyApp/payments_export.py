"""
Export utilities for Fee Collection & Receipts Register.
Generates executive Landscape A4 PDF and multi-sheet Excel (.xlsx) documents matching
the exact institutional snapshot design of Sutawane Classes software.
"""

import io
from datetime import datetime
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

from .export_theme import (
    COLOR_NAVY_PRIMARY,
    COLOR_NAVY_SECONDARY,
    COLOR_GREEN_PAID,
    COLOR_RED_PENDING,
    COLOR_BG_TOTALS,
    COLOR_BORDER,
    COLOR_SLATE_TEXT,
    format_currency_inr,
    format_number_inr,
    build_executive_pdf_header,
    ExecutiveLandscapeCanvas,
    FONT_FAMILY,
    FONT_FAMILY_BOLD,
)


def export_payments_to_excel(payments_list, meta=None):
    """
    Generates an executive Openpyxl Excel workbook (.xlsx) containing filtered fee collection records.
    Features:
    - Multi-sheet data isolation:
      * Sheet 1: Master Collections Ledger (All matching active filters)
      * Sheet 2+: Payment Mode Breakdown (UPI, Cash, Bank Transfer, Cheque)
                 OR Branch-specific breakdown (when multiple branches present)
    - Row heights: Title=28, Meta=18, Header=24, Rows=20, Totals=24
    - Auto column widths padded by +4 characters
    - Amount Collected in bold with currency formatting
    - Reversal/Voided status in Red/Rose (#DC2626)
    - Reconciled totals row with #F1F5F9 fill and double bottom border
    """
    meta = meta or {}
    branch_name = meta.get('branch_name', 'All Branches')
    session_name = meta.get('session_name', 'All Sessions')
    now_str = datetime.now().strftime("%d-%b-%Y %I:%M %p")

    wb = Workbook()

    bold_font = Font(name="Calibri", size=10, bold=True)
    normal_font = Font(name="Calibri", size=10)
    paid_font = Font(name="Calibri", size=10, bold=True, color="16A34A")
    void_font = Font(name="Calibri", size=10, bold=True, color="DC2626")
    totals_bold = Font(name="Calibri", size=11, bold=True, color="1A2B4C")
    totals_paid = Font(name="Calibri", size=11, bold=True, color="16A34A")

    thin_border = Border(
        left=Side(style='thin', color='CBD5E1'),
        right=Side(style='thin', color='CBD5E1'),
        top=Side(style='thin', color='CBD5E1'),
        bottom=Side(style='thin', color='CBD5E1')
    )
    totals_border = Border(
        left=Side(style='thin', color='CBD5E1'),
        right=Side(style='thin', color='CBD5E1'),
        top=Side(style='medium', color='1A2B4C'),
        bottom=Side(style='double', color='1A2B4C')
    )
    totals_fill = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")

    headers = [
        '#', 'Receipt No.', 'Payment Date', 'Student Name', 'Roll No.', 'Class / Course',
        'Campus Branch', 'Academic Session', 'Payment Mode', 'Reference / Txn No.',
        'Amount Collected (Rs.)', 'Receipt Status', 'Notes / Remarks'
    ]

    def populate_sheet(ws, sheet_title, records, filter_label):
        ws.views.sheetView[0].showGridLines = True

        title_font = Font(name="Calibri", size=14, bold=True, color="1A2B4C")
        meta_font = Font(name="Calibri", size=10, italic=True, color="64748B")
        hdr_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        navy_fill = PatternFill(start_color="28375C", end_color="28375C", fill_type="solid")

        max_col_letter = get_column_letter(len(headers))

        # Title Block
        ws.merge_cells(f"A1:{max_col_letter}1")
        ws["A1"] = f"SUTAWANE CLASSES • {sheet_title.upper()} REGISTER"
        ws["A1"].font = title_font
        ws["A1"].alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[1].height = 28

        ws.merge_cells(f"A2:{max_col_letter}2")
        ws["A2"] = f"Scope: {filter_label} | Generated on: {now_str} | Total Receipts: {len(records)}"
        ws["A2"].font = meta_font
        ws["A2"].alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[2].height = 18

        ws.row_dimensions[3].height = 8

        # Headers
        ws.row_dimensions[4].height = 24
        for col_idx, h in enumerate(headers, 1):
            cell = ws.cell(row=4, column=col_idx, value=h)
            cell.font = hdr_font
            cell.fill = navy_fill
            cell.alignment = Alignment(horizontal="center", vertical="center")

        # Data Rows
        cur_row = 5
        tot_amount = 0.0
        active_count = 0
        void_count = 0

        for idx, p in enumerate(records, 1):
            amt = float(p.total_amount or 0.0)
            if not p.is_reversed:
                tot_amount += amt
                active_count += 1
            else:
                void_count += 1

            roll_no = p.admission.roll_number if p.admission and p.admission.roll_number else (p.student.student_code or '')
            std_name = p.admission.standard if p.admission and p.admission.standard else 'General'
            b_name = p.branch.name if p.branch else 'Main Campus'
            s_name = p.session.name if p.session else ''
            p_date = p.payment_date.strftime("%d-%b-%Y") if p.payment_date else ''
            status_text = 'VOIDED' if p.is_reversed else 'ACTIVE'

            row_vals = [
                idx,
                p.receipt_number,
                p_date,
                p.student.full_name,
                roll_no,
                std_name,
                b_name,
                s_name,
                p.payment_mode,
                p.reference_number or '',
                amt,
                status_text,
                p.notes or ''
            ]

            ws.row_dimensions[cur_row].height = 20
            for col_idx, val in enumerate(row_vals, 1):
                cell = ws.cell(row=cur_row, column=col_idx, value=val)
                cell.font = normal_font
                cell.border = thin_border
                cell.alignment = Alignment(vertical="center")

                if col_idx in (1, 3, 5, 9, 12):
                    cell.alignment = Alignment(horizontal="center", vertical="center")
                elif col_idx == 11:
                    cell.alignment = Alignment(horizontal="right", vertical="center")
                    cell.number_format = '₹#,##0.00'
                    cell.font = paid_font if not p.is_reversed else void_font

                if col_idx == 12:
                    cell.font = void_font if p.is_reversed else paid_font

            cur_row += 1

        # Totals Row
        ws.row_dimensions[cur_row].height = 24
        ws.merge_cells(f"A{cur_row}:J{cur_row}")
        t_label = ws.cell(row=cur_row, column=1, value=f"CONSOLIDATED NET COLLECTIONS ({active_count} Active Receipts, {void_count} Voided)")
        t_label.font = totals_bold
        t_label.alignment = Alignment(horizontal="right", vertical="center")
        t_label.fill = totals_fill

        for c in range(1, 11):
            cell = ws.cell(row=cur_row, column=c)
            cell.border = totals_border
            cell.fill = totals_fill

        t_amt_cell = ws.cell(row=cur_row, column=11, value=tot_amount)
        t_amt_cell.font = totals_paid
        t_amt_cell.border = totals_border
        t_amt_cell.fill = totals_fill
        t_amt_cell.number_format = '₹#,##0.00'
        t_amt_cell.alignment = Alignment(horizontal="right", vertical="center")

        ws.cell(row=cur_row, column=12).border = totals_border
        ws.cell(row=cur_row, column=12).fill = totals_fill
        ws.cell(row=cur_row, column=13).border = totals_border
        ws.cell(row=cur_row, column=13).fill = totals_fill

        # Auto-fit Column Widths
        for col in ws.columns:
            col_letter = get_column_letter(col[0].column)
            max_len = 0
            for cell in col:
                if cell.row in (1, 2, 3):
                    continue
                v_str = str(cell.value or '')
                if len(v_str) > max_len:
                    max_len = len(v_str)
            ws.column_dimensions[col_letter].width = max(max_len + 4, 12)

    # 1. Master Consolidated Sheet
    ws_master = wb.active
    ws_master.title = "Master Collections Ledger"
    populate_sheet(ws_master, "Fee Collections Master Ledger", payments_list, f"{branch_name} • {session_name}")

    # 2. Mode-Wise Data Isolation Sheets
    mode_buckets = {}
    for p in payments_list:
        m = p.payment_mode or 'OTHER'
        mode_buckets.setdefault(m, []).append(p)

    if len(mode_buckets) > 1:
        for mode_name, mode_records in sorted(mode_buckets.items()):
            sheet_title = f"{mode_name} Collections"[:30]
            ws_mode = wb.create_sheet(title=sheet_title)
            populate_sheet(ws_mode, f"{mode_name} Collections", mode_records, f"{mode_name} • {branch_name}")

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output.getvalue()


def export_payments_to_pdf(payments_list, meta=None):
    """
    Generates an executive Landscape A4 PDF document for Fee Collections:
    - Left institutional title block with logo
    - Right scope & records metadata card
    - Amber accent line + Navy divider
    - Landscape table with Green paid amounts and Red voided badges
    - Reconciled totals row
    - Two-pass 'Page X of Y' running footer
    """
    meta = meta or {}
    branch_name = meta.get('branch_name', 'All Branches')
    session_name = meta.get('session_name', 'All Sessions')

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=20,
        rightMargin=20,
        topMargin=20,
        bottomMargin=30,
    )

    styles = getSampleStyleSheet()

    hdr_style = ParagraphStyle(
        'PayHdrCenter',
        parent=styles['Normal'],
        fontName=FONT_FAMILY_BOLD,
        fontSize=7.5,
        leading=9.5,
        textColor=colors.white,
        alignment=1,
    )
    hdr_right_style = ParagraphStyle(
        'PayHdrRight',
        parent=styles['Normal'],
        fontName=FONT_FAMILY_BOLD,
        fontSize=7.5,
        leading=9.5,
        textColor=colors.white,
        alignment=2,
    )
    cell_normal = ParagraphStyle(
        'PayCellNormal',
        parent=styles['Normal'],
        fontName=FONT_FAMILY,
        fontSize=7,
        leading=9,
        textColor=colors.HexColor(COLOR_SLATE_TEXT),
    )
    cell_bold = ParagraphStyle(
        'PayCellBold',
        parent=styles['Normal'],
        fontName=FONT_FAMILY_BOLD,
        fontSize=7,
        leading=9,
        textColor=colors.HexColor(COLOR_SLATE_TEXT),
    )
    cell_center = ParagraphStyle(
        'PayCellCenter',
        parent=styles['Normal'],
        fontName=FONT_FAMILY,
        fontSize=7,
        leading=9,
        textColor=colors.HexColor(COLOR_SLATE_TEXT),
        alignment=1,
    )
    cell_right = ParagraphStyle(
        'PayCellRight',
        parent=styles['Normal'],
        fontName=FONT_FAMILY,
        fontSize=7,
        leading=9,
        textColor=colors.HexColor(COLOR_SLATE_TEXT),
        alignment=2,
    )
    cell_paid = ParagraphStyle(
        'PayCellPaid',
        parent=styles['Normal'],
        fontName=FONT_FAMILY_BOLD,
        fontSize=7,
        leading=9,
        textColor=colors.HexColor(COLOR_GREEN_PAID),
        alignment=2,
    )
    cell_void = ParagraphStyle(
        'PayCellVoid',
        parent=styles['Normal'],
        fontName=FONT_FAMILY_BOLD,
        fontSize=7,
        leading=9,
        textColor=colors.HexColor(COLOR_RED_PENDING),
        alignment=1,
    )
    cell_active = ParagraphStyle(
        'PayCellActive',
        parent=styles['Normal'],
        fontName=FONT_FAMILY_BOLD,
        fontSize=7,
        leading=9,
        textColor=colors.HexColor(COLOR_GREEN_PAID),
        alignment=1,
    )

    tot_collected = sum(p.total_amount for p in payments_list if not p.is_reversed)
    total_receipts = len(payments_list)
    voided_receipts = sum(1 for p in payments_list if p.is_reversed)

    # 1. Executive PDF Header
    flowables = build_executive_pdf_header(
        "Official Fee Collection & Receipts Register",
        meta={
            'branch_name': branch_name,
            'session_name': session_name,
            'branch_logo': meta.get('branch_logo'),
            'records_count': total_receipts,
        },
        report_badge_label="NET AMOUNT:",
        report_badge_value=format_currency_inr(tot_collected),
    )

    # 2. Table Headers & Column Widths (Total: 802pt)
    # Col Widths: #=20, Receipt=110, Date=55, Student=130, Roll=55, Class=80, Branch=85, Mode=55, Amount=80, Status=50
    col_widths = [20, 110, 55, 130, 55, 80, 85, 55, 80, 52]

    table_data = [[
        Paragraph("#", hdr_style),
        Paragraph("Receipt No.", hdr_style),
        Paragraph("Date", hdr_style),
        Paragraph("Student Name", hdr_style),
        Paragraph("Roll No.", hdr_style),
        Paragraph("Class / Course", hdr_style),
        Paragraph("Campus Branch", hdr_style),
        Paragraph("Mode", hdr_style),
        Paragraph("Amount (Rs.)", hdr_right_style),
        Paragraph("Status", hdr_style),
    ]]

    for idx, p in enumerate(payments_list, 1):
        amt = float(p.total_amount or 0.0)
        roll_no = p.admission.roll_number if p.admission and p.admission.roll_number else (p.student.student_code or '')
        std_name = p.admission.standard if p.admission and p.admission.standard else 'General'
        b_name = p.branch.name if p.branch else 'Main Campus'
        p_date = p.payment_date.strftime("%d-%b-%Y") if p.payment_date else ''
        status_par = Paragraph("VOIDED", cell_void) if p.is_reversed else Paragraph("ACTIVE", cell_active)
        amt_par = Paragraph(format_currency_inr(amt), cell_void if p.is_reversed else cell_paid)

        table_data.append([
            Paragraph(str(idx), cell_center),
            Paragraph(p.receipt_number, cell_bold),
            Paragraph(p_date, cell_center),
            Paragraph(p.student.full_name, cell_bold),
            Paragraph(roll_no, cell_center),
            Paragraph(std_name, cell_normal),
            Paragraph(b_name, cell_normal),
            Paragraph(p.payment_mode, cell_center),
            amt_par,
            status_par,
        ])

    # Totals Row
    table_data.append([
        Paragraph(f"<b>TOTALS: {total_receipts} Receipts ({voided_receipts} Voided)</b>", cell_bold),
        "", "", "", "", "", "",
        Paragraph("<b>NET:</b>", cell_right),
        Paragraph(f"<b>{format_currency_inr(tot_collected)}</b>", cell_paid),
        "",
    ])

    pdf_table = Table(table_data, colWidths=col_widths, repeatRows=1)

    t_style = [
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(COLOR_NAVY_SECONDARY)),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('GRID', (0, 0), (-1, -2), 0.5, colors.HexColor(COLOR_BORDER)),
        ('LINEBELOW', (0, 0), (-1, 0), 1, colors.HexColor(COLOR_NAVY_PRIMARY)),
        ('SPAN', (0, -1), (6, -1)),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor(COLOR_BG_TOTALS)),
        ('LINEABOVE', (0, -1), (-1, -1), 1, colors.HexColor(COLOR_NAVY_PRIMARY)),
        ('LINEBELOW', (0, -1), (-1, -1), 1.5, colors.HexColor(COLOR_NAVY_PRIMARY)),
    ]

    # Alternating row background
    for r_idx in range(1, len(table_data) - 1):
        if r_idx % 2 == 0:
            t_style.append(('BACKGROUND', (0, r_idx), (-1, r_idx), colors.HexColor('#F8FAFC')))

    pdf_table.setStyle(TableStyle(t_style))
    flowables.append(pdf_table)

    doc.build(flowables, canvasmaker=ExecutiveLandscapeCanvas)
    buffer.seek(0)
    return buffer.getvalue()
