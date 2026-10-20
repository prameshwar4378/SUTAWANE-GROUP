"""
Export utilities for Student Fee Dues Register.
Generates executive Landscape PDF and multi-sheet Excel (.xlsx) documents matching
the exact institutional snapshot design of Sutawane Classes software.
"""

import io
from datetime import datetime
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
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
    build_executive_pdf_header,
    ExecutiveLandscapeCanvas,
    format_excel_worksheet,
)


def export_dues_to_excel(dues_list, meta=None):
    """
    Generates an Excel workbook (.xlsx) containing filtered student dues.
    Features:
    - Multi-sheet data isolation:
      * Sheet 1: Consolidated Pending Dues (all matching active filter)
      * Sheet 2+: Dedicated sheets grouped by Campus Branch (e.g. Vaijapur, Nagpur)
                 OR Course-wise summary if single branch.
    - Currency formatting: ₹#,##0
    - Amount Paid in Green (#16A34A)
    - Remaining Balance in Red (#DC2626)
    - Professional Totals row with #F1F5F9 fill and double bottom border.
    """
    wb = Workbook()
    meta = meta or {}
    branch_name = meta.get('branch_name', 'All Branches')
    session_name = meta.get('session_name', 'All Sessions')
    now_str = datetime.now().strftime("%d-%b-%Y %I:%M %p")

    # Font and Fill definitions
    bold_font = Font(name="Calibri", size=10, bold=True)
    normal_font = Font(name="Calibri", size=10)
    paid_font = Font(name="Calibri", size=10, bold=True, color="16A34A")
    due_font = Font(name="Calibri", size=10, bold=True, color="DC2626")
    totals_bold = Font(name="Calibri", size=11, bold=True, color="1A2B4C")
    totals_paid = Font(name="Calibri", size=11, bold=True, color="16A34A")
    totals_due = Font(name="Calibri", size=11, bold=True, color="DC2626")

    thin_border = Border(
        left=Side(style='thin', color='CBD5E1'),
        right=Side(style='thin', color='CBD5E1'),
        top=Side(style='thin', color='CBD5E1'),
        bottom=Side(style='thin', color='CBD5E1')
    )
    totals_border = Border(
        top=Side(style='medium', color='1A2B4C'),
        bottom=Side(style='double', color='1A2B4C'),
        left=Side(style='thin', color='CBD5E1'),
        right=Side(style='thin', color='CBD5E1')
    )
    totals_fill = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")

    headers = [
        ("#", 6),
        ("Student Name", 22),
        ("Roll Number", 14),
        ("Class / Standard", 16),
        ("Branch Location", 20),
        ("Academic Session", 14),
        ("Parent Mobile", 15),
        ("Due Date", 14),
        ("Session Fee (₹)", 16),
        ("Amount Paid (₹)", 16),
        ("Balance Due (₹)", 18),
        ("Due Status", 14),
    ]

    def populate_sheet(ws, records, sheet_title, sheet_scope_label):
        ws.title = sheet_title[:31]  # Excel 31-char sheet name limit
        header_row = 4

        # Add Header row
        for col_idx, (header_text, width) in enumerate(headers, start=1):
            cell = ws.cell(row=header_row, column=col_idx, value=header_text)
            cell.alignment = Alignment(horizontal="center" if col_idx in [1, 3, 4, 6, 7, 8, 12] else ("left" if col_idx in [2, 5] else "right"), vertical="center")

        current_row = 5
        tot_fee = 0.0
        tot_paid = 0.0
        tot_bal = 0.0

        for idx, d in enumerate(records, start=1):
            f_amt = float(d.get('amount_due', 0.0))
            p_amt = float(d.get('amount_paid', 0.0))
            b_amt = float(d.get('balance_remaining', 0.0))
            status = d.get('status', 'DUE')

            tot_fee += f_amt
            tot_paid += p_amt
            tot_bal += b_amt

            row_vals = [
                idx,
                d.get('student_name', ''),
                d.get('roll_number', '—'),
                d.get('standard', '—'),
                d.get('branch_name', '—'),
                d.get('session_name', '—'),
                d.get('parent_phone', '—'),
                d.get('due_date_formatted', '—'),
                f_amt,
                p_amt,
                b_amt,
                status,
            ]

            ws.row_dimensions[current_row].height = 20
            for col_idx, val in enumerate(row_vals, start=1):
                cell = ws.cell(row=current_row, column=col_idx, value=val)
                cell.border = thin_border

                if col_idx in [9, 10, 11]:
                    cell.number_format = '₹#,##0'
                    cell.alignment = Alignment(horizontal="right", vertical="center")
                    if col_idx == 10:
                        cell.font = paid_font
                    elif col_idx == 11:
                        cell.font = due_font
                    else:
                        cell.font = bold_font
                elif col_idx in [1, 3, 4, 6, 7, 8, 12]:
                    cell.alignment = Alignment(horizontal="center", vertical="center")
                    cell.font = due_font if col_idx == 12 and status in ('DUE', 'OVERDUE') else normal_font
                else:
                    cell.alignment = Alignment(horizontal="left", vertical="center")
                    cell.font = bold_font if col_idx == 2 else normal_font

            current_row += 1

        # Totals Row
        ws.row_dimensions[current_row].height = 24
        ws.merge_cells(start_row=current_row, start_column=1, end_row=current_row, end_column=8)
        lbl_cell = ws.cell(row=current_row, column=1, value=f"TOTALS ({len(records)} accounts)")
        lbl_cell.font = totals_bold
        lbl_cell.alignment = Alignment(horizontal="right", vertical="center")

        c_fee = ws.cell(row=current_row, column=9, value=tot_fee)
        c_fee.font = totals_bold
        c_fee.number_format = '₹#,##0'
        c_fee.alignment = Alignment(horizontal="right", vertical="center")

        c_paid = ws.cell(row=current_row, column=10, value=tot_paid)
        c_paid.font = totals_paid
        c_paid.number_format = '₹#,##0'
        c_paid.alignment = Alignment(horizontal="right", vertical="center")

        c_bal = ws.cell(row=current_row, column=11, value=tot_bal)
        c_bal.font = totals_due
        c_bal.number_format = '₹#,##0'
        c_bal.alignment = Alignment(horizontal="right", vertical="center")

        ws.cell(row=current_row, column=12, value="")

        for col in range(1, 13):
            c = ws.cell(row=current_row, column=col)
            c.border = totals_border
            c.fill = totals_fill

        # Apply Title Banner and Column Widths
        meta_str = f"SCOPE: {sheet_scope_label}  |  DATE: {now_str}  |  TOTAL PENDING: {len(records)} accounts"
        format_excel_worksheet(ws, "SUTAWANE CLASSES — STUDENT FEE DUES & OUTSTANDING BALANCES", meta_str, header_row=4)

    # 1. Main Sheet: All Filtered Dues
    ws_main = wb.active
    populate_sheet(ws_main, dues_list, "Consolidated Dues", f"{branch_name} • {session_name}")

    # 2. Multi-Sheet Data Isolation: Group by Branch if multiple branches exist
    branches_present = sorted(list({d.get('branch_name') for d in dues_list if d.get('branch_name') and d.get('branch_name') != '—'}))
    if len(branches_present) > 1:
        for b_name in branches_present:
            branch_records = [d for d in dues_list if d.get('branch_name') == b_name]
            if branch_records:
                ws_branch = wb.create_sheet(title=b_name[:31])
                populate_sheet(ws_branch, branch_records, b_name, f"{b_name} • {session_name}")
    else:
        # If single branch, create Course-wise Summary Sheet
        ws_courses = wb.create_sheet(title="Course Summary")
        ws_courses.views.sheetView[0].showGridLines = True
        c_headers = [("#", 6), ("Class / Standard", 22), ("Pending Students", 18), ("Total Fees (₹)", 18), ("Amount Paid (₹)", 18), ("Balance Due (₹)", 20)]
        for col_idx, (h_text, _) in enumerate(c_headers, start=1):
            cell = ws_courses.cell(row=4, column=col_idx, value=h_text)
            cell.alignment = Alignment(horizontal="center" if col_idx in [1, 3] else ("left" if col_idx == 2 else "right"), vertical="center")

        std_map = {}
        for d in dues_list:
            std = d.get('standard') or 'General'
            if std not in std_map:
                std_map[std] = {'count': 0, 'fee': 0.0, 'paid': 0.0, 'bal': 0.0}
            std_map[std]['count'] += 1
            std_map[std]['fee'] += float(d.get('amount_due', 0.0))
            std_map[std]['paid'] += float(d.get('amount_paid', 0.0))
            std_map[std]['bal'] += float(d.get('balance_remaining', 0.0))

        c_row = 5
        tot_std_fee = 0.0
        tot_std_paid = 0.0
        tot_std_bal = 0.0
        for idx, (std_name, s_data) in enumerate(sorted(std_map.items()), start=1):
            tot_std_fee += s_data['fee']
            tot_std_paid += s_data['paid']
            tot_std_bal += s_data['bal']
            ws_courses.row_dimensions[c_row].height = 20
            row_items = [idx, std_name, s_data['count'], s_data['fee'], s_data['paid'], s_data['bal']]
            for col_idx, val in enumerate(row_items, start=1):
                c = ws_courses.cell(row=c_row, column=col_idx, value=val)
                c.border = thin_border
                if col_idx in [4, 5, 6]:
                    c.number_format = '₹#,##0'
                    c.alignment = Alignment(horizontal="right", vertical="center")
                    c.font = paid_font if col_idx == 5 else (due_font if col_idx == 6 else bold_font)
                elif col_idx in [1, 3]:
                    c.alignment = Alignment(horizontal="center", vertical="center")
                    c.font = bold_font if col_idx == 3 else normal_font
                else:
                    c.alignment = Alignment(horizontal="left", vertical="center")
                    c.font = bold_font
            c_row += 1

        # Summary Row
        ws_courses.row_dimensions[c_row].height = 24
        ws_courses.merge_cells(start_row=c_row, start_column=1, end_row=c_row, end_column=3)
        lbl = ws_courses.cell(row=c_row, column=1, value="TOTALS")
        lbl.font = totals_bold
        lbl.alignment = Alignment(horizontal="right", vertical="center")
        
        c1 = ws_courses.cell(row=c_row, column=4, value=tot_std_fee)
        c1.font = totals_bold
        c1.number_format = '₹#,##0'
        c1.alignment = Alignment(horizontal="right", vertical="center")

        c2 = ws_courses.cell(row=c_row, column=5, value=tot_std_paid)
        c2.font = totals_paid
        c2.number_format = '₹#,##0'
        c2.alignment = Alignment(horizontal="right", vertical="center")

        c3 = ws_courses.cell(row=c_row, column=6, value=tot_std_bal)
        c3.font = totals_due
        c3.number_format = '₹#,##0'
        c3.alignment = Alignment(horizontal="right", vertical="center")

        for col in range(1, 7):
            c = ws_courses.cell(row=c_row, column=col)
            c.border = totals_border
            c.fill = totals_fill

        format_excel_worksheet(ws_courses, "SUTAWANE CLASSES — COURSE-WISE DUES SUMMARY", f"SCOPE: {branch_name} • {session_name}  |  DATE: {now_str}", header_row=4)

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output.getvalue()


def export_dues_to_pdf(dues_list, meta=None):
    """
    Generates an executive Landscape A4 PDF document matching the snapshot design.
    Features:
    - Official Header with Sutawane Logo, Title, Subtitle, Tagline
    - Institutional Scope & Metadata Box on the right
    - Vibrant Orange and Navy Accent Bar
    - Amount Paid in Green (#16A34A)
    - Balance Due (INR) in Red (#DC2626)
    - Summary Totals row with matching colors and formatting
    - Two-pass Running Page Footer (Page X of Y)
    """
    output = io.BytesIO()
    doc = SimpleDocTemplate(
        output,
        pagesize=landscape(A4),
        leftMargin=18,
        rightMargin=18,
        topMargin=18,
        bottomMargin=26,
    )

    meta = meta or {}
    branch_name = meta.get('branch_name', 'All Branches')
    session_name = meta.get('session_name', 'All Sessions')
    date_str = meta.get('date_str') or datetime.now().strftime("%d %b %Y, %I:%M %p")

    styles = getSampleStyleSheet()
    cell_normal = ParagraphStyle('CellNorm', parent=styles['Normal'], fontName='Helvetica', fontSize=8, leading=10, textColor=colors.HexColor(COLOR_SLATE_TEXT))
    cell_bold = ParagraphStyle('CellBld', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8, leading=10, textColor=colors.HexColor(COLOR_SLATE_TEXT))
    cell_green = ParagraphStyle('CellGrn', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8, leading=10, textColor=colors.HexColor(COLOR_GREEN_PAID), alignment=2)
    cell_red = ParagraphStyle('CellRed', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8, leading=10, textColor=colors.HexColor(COLOR_RED_PENDING), alignment=2)
    cell_fee = ParagraphStyle('CellFee', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8, leading=10, textColor=colors.HexColor(COLOR_SLATE_TEXT), alignment=2)
    cell_center = ParagraphStyle('CellCtr', parent=styles['Normal'], fontName='Helvetica', fontSize=8, leading=10, alignment=1)
    cell_status = ParagraphStyle('CellStat', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=7.5, leading=9, textColor=colors.HexColor('#2563EB'), alignment=1)

    story = []

    # 1. Executive Snapshot Header
    meta_dict = {
        'institute_name': meta.get('institute_name') or 'SUTAWANE CLASSES VAIJAPUR',
        'branch_name': branch_name,
        'session_name': session_name,
        'date_str': date_str,
        'records_count': len(dues_list),
    }
    story.extend(build_executive_pdf_header(
        "STUDENT FEE DUES & OUTSTANDING BALANCES REPORT",
        meta=meta_dict,
        report_badge_label="RECORDS:",
        report_badge_value=f"{len(dues_list)} Students Pending"
    ))

    # 2. Table Data
    table_data = [
        [
            "#",
            "Student Name",
            "Roll No.",
            "Class",
            "Branch",
            "Phone",
            "Due Date",
            "Session Fee",
            "Amount Paid",
            "Balance Due (INR)",
            "Status"
        ]
    ]

    total_fee = 0.0
    total_paid = 0.0
    total_balance = 0.0

    for idx, d in enumerate(dues_list, start=1):
        f_amt = float(d.get('amount_due', 0.0))
        p_amt = float(d.get('amount_paid', 0.0))
        b_amt = float(d.get('balance_remaining', 0.0))

        total_fee += f_amt
        total_paid += p_amt
        total_balance += b_amt

        table_data.append([
            Paragraph(str(idx), cell_center),
            Paragraph(f"<b>{d.get('student_name', '')}</b>", cell_bold),
            Paragraph(str(d.get('roll_number', '—')), cell_center),
            Paragraph(str(d.get('standard', '—')), cell_center),
            Paragraph(str(d.get('branch_name', '—')), cell_normal),
            Paragraph(str(d.get('parent_phone', '—')), cell_center),
            Paragraph(str(d.get('due_date_formatted', '—')), cell_center),
            Paragraph(f"{int(f_amt):,}", cell_fee),
            Paragraph(f"{int(p_amt):,}", cell_green),
            Paragraph(f"{int(b_amt):,}", cell_red),
            Paragraph(str(d.get('status', 'DUE')), cell_status),
        ])

    # 3. Totals Row
    table_data.append([
        "",
        Paragraph(f"<b>TOTALS ({len(dues_list)} accounts)</b>", cell_bold),
        "", "", "", "", "",
        Paragraph(f"<b>{int(total_fee):,}</b>", cell_fee),
        Paragraph(f"<b>{int(total_paid):,}</b>", cell_green),
        Paragraph(f"<b>{int(total_balance):,}</b>", cell_red),
        "",
    ])

    # Table Column Widths (Sum = 804 points, fits Landscape A4)
    col_widths = [24, 134, 66, 62, 114, 76, 66, 76, 70, 76, 44]

    t = Table(table_data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(COLOR_NAVY_SECONDARY)),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 5.5),
        ('TOPPADDING', (0, 0), (-1, 0), 5.5),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
        ('ALIGN', (2, 0), (3, -1), 'CENTER'),
        ('ALIGN', (5, 0), (6, -1), 'CENTER'),
        ('ALIGN', (7, 0), (9, -1), 'RIGHT'),
        ('ALIGN', (10, 0), (10, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor(COLOR_BORDER)),
        ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, colors.HexColor('#F8FAFC')]),
        ('TOPPADDING', (0, 1), (-1, -1), 4.5),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 4.5),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor(COLOR_BG_TOTALS)),
        ('LINEABOVE', (0, -1), (-1, -1), 1.25, colors.HexColor(COLOR_NAVY_PRIMARY)),
        ('LINEBELOW', (0, -1), (-1, -1), 1.25, colors.HexColor(COLOR_NAVY_PRIMARY)),
    ]))

    story.append(t)
    doc.build(story, canvasmaker=ExecutiveLandscapeCanvas)
    output.seek(0)
    return output.getvalue()
