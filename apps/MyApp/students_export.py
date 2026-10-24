"""
Export utilities for Students Directory & Enrollment Register.
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


def export_students_to_excel(students_data, meta=None):
    """
    Generates an executive Openpyxl Excel workbook (.xlsx) containing filtered student directory records.
    Features:
    - Multi-sheet data isolation:
      * Sheet 1: Master Directory (All matching active filters)
      * Sheet 2+: Branch-specific sheets (when multiple branches present)
                 OR Standard/Class-wise sheets (when single branch selected)
    - Row heights: Title=28, Meta=18, Header=24, Rows=20, Totals=24
    - Auto column widths padded by +4 characters
    - Paid Fees in Green (#16A34A)
    - Pending Dues in Red (#DC2626)
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
        left=Side(style='thin', color='CBD5E1'),
        right=Side(style='thin', color='CBD5E1'),
        top=Side(style='medium', color='1A2B4C'),
        bottom=Side(style='double', color='1A2B4C')
    )
    totals_fill = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")

    headers = [
        '#', 'Student Name', 'Roll No.', 'Student Code', 'Class / Course',
        'Campus Branch', 'Academic Session', 'Parent Contact', 'Student Contact',
        'Agreed Fees (Rs.)', 'Paid Amount (Rs.)', 'Session Pending (Rs.)',
        'Overall Due (Rs.)', 'Fee Status', 'Status'
    ]

    def populate_sheet(ws, sheet_title, records, scope_note):
        ws.title = sheet_title[:31]  # Excel limits tab names to 31 chars
        ws.views.sheetView[0].showGridLines = True

        # 1. Title Block
        max_col_letter = get_column_letter(len(headers))
        ws.merge_cells(f"A1:{max_col_letter}1")
        ws["A1"] = f"SUTAWANE CLASSES — STUDENTS ENROLLMENT DIRECTORY"
        ws["A1"].font = Font(name="Calibri", size=13, bold=True, color="1A2B4C")
        ws["A1"].alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[1].height = 28

        ws.merge_cells(f"A2:{max_col_letter}2")
        sess_pend = meta.get('session_pending_total')
        ov_pend = meta.get('overall_pending_total')
        meta_parts = [
            f"Scope: {scope_note}",
            f"Export Date: {now_str}",
            f"Enrolled Records: {len(records)}",
        ]
        if sess_pend is not None:
            meta_parts.append(f"Session Pending Dues: ₹{float(sess_pend):,.0f}")
        if ov_pend is not None:
            meta_parts.append(f"All-Sessions Overall Pending: ₹{float(ov_pend):,.0f}")
        ws["A2"] = " | ".join(meta_parts)
        ws["A2"].font = Font(name="Calibri", size=9.5, italic=True, color="64748B")
        ws["A2"].alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[2].height = 18

        ws.row_dimensions[3].height = 8

        # 2. Header Row
        ws.row_dimensions[4].height = 24
        header_fill = PatternFill(start_color="28375C", end_color="28375C", fill_type="solid")
        header_font = Font(name="Calibri", size=10, bold=True, color="FFFFFF")

        for col_idx, h_text in enumerate(headers, 1):
            cell = ws.cell(row=4, column=col_idx, value=h_text)
            cell.font = header_font
            cell.fill = header_fill
            cell.border = thin_border
            align_h = "center" if col_idx in [1, 3, 4, 8, 9, 14, 15] else ("right" if col_idx in [10, 11, 12, 13] else "left")
            cell.alignment = Alignment(horizontal=align_h, vertical="center")

        # 3. Data Rows
        tot_agreed = 0.0
        tot_paid = 0.0
        tot_pending = 0.0
        tot_overall = 0.0

        for idx, item in enumerate(records, 1):
            st = item.get('student')
            adm = item.get('admission')
            
            st_name = st.full_name if st else '—'
            st_code = st.student_code if st else '—'
            p_phone = st.parent_phone if st else '—'
            s_phone = st.student_phone or '—' if st else '—'
            
            roll_no = adm.roll_number if adm else '—'
            std_name = adm.standard if adm else '—'
            b_name = adm.branch.name if adm and adm.branch else '—'
            s_name = adm.session.display_name if adm and adm.session else (adm.session.name if adm and adm.session else '—')
            is_act = "Active" if adm and adm.is_active else "Archived"

            agreed = float(item.get('total_fees', 0.0))
            paid = float(item.get('paid_fees', 0.0))
            pending = float(item.get('pending_fees', 0.0))
            overall = float(item.get('overall_pending', 0.0))
            f_status = item.get('fee_status', 'PAID')

            tot_agreed += agreed
            tot_paid += paid
            tot_pending += pending
            tot_overall += overall

            row_cells = [
                idx, st_name, roll_no, st_code, std_name,
                b_name, s_name, p_phone, s_phone,
                agreed, paid, pending, overall, f_status, is_act
            ]

            row_num = 4 + idx
            ws.row_dimensions[row_num].height = 20

            for col_idx, val in enumerate(row_cells, 1):
                cell = ws.cell(row=row_num, column=col_idx, value=val)
                cell.border = thin_border

                if col_idx in [10, 11, 12, 13]:
                    cell.number_format = '₹#,##0'
                    cell.alignment = Alignment(horizontal="right", vertical="center")
                    if col_idx == 11:
                        cell.font = paid_font
                    elif col_idx in [12, 13]:
                        cell.font = due_font if val > 0 else normal_font
                    else:
                        cell.font = bold_font
                elif col_idx in [1, 3, 4, 8, 9, 14, 15]:
                    cell.font = normal_font
                    cell.alignment = Alignment(horizontal="center", vertical="center")
                elif col_idx == 2:
                    cell.font = bold_font
                    cell.alignment = Alignment(horizontal="left", vertical="center")
                else:
                    cell.font = normal_font
                    cell.alignment = Alignment(horizontal="left", vertical="center")

        # 4. Totals Row
        tot_row_num = 4 + len(records) + 1
        ws.row_dimensions[tot_row_num].height = 24

        tot_vals = [
            'TOTAL', f"{len(records)} Enrolled", '', '', '',
            '', '', '', '',
            tot_agreed, tot_paid, tot_pending, tot_overall, '', ''
        ]

        for col_idx, val in enumerate(tot_vals, 1):
            cell = ws.cell(row=tot_row_num, column=col_idx, value=val)
            cell.border = totals_border
            cell.fill = totals_fill

            if col_idx in [10, 11, 12, 13]:
                cell.number_format = '₹#,##0'
                cell.alignment = Alignment(horizontal="right", vertical="center")
                if col_idx == 11:
                    cell.font = totals_paid
                elif col_idx in [12, 13]:
                    cell.font = totals_due
                else:
                    cell.font = totals_bold
            elif col_idx in [1, 2]:
                cell.font = totals_bold
                cell.alignment = Alignment(horizontal="left", vertical="center")
            else:
                cell.alignment = Alignment(horizontal="center", vertical="center")

        # 5. Auto Column Widths
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

    # Sheet 1: Master Consolidated Directory
    ws1 = wb.active
    populate_sheet(ws1, "Master Directory", students_data, f"{branch_name} • {session_name}")

    # Multi-Sheet Data Isolation:
    # Check if multiple branches exist in the dataset
    branch_buckets = {}
    standard_buckets = {}
    for item in students_data:
        adm = item.get('admission')
        b_title = adm.branch.name if adm and adm.branch else 'Unassigned'
        std_title = adm.standard if adm and adm.standard else 'General'
        
        branch_buckets.setdefault(b_title, []).append(item)
        standard_buckets.setdefault(std_title, []).append(item)

    if len(branch_buckets) > 1:
        # Grouped by Branch tabs
        for b_name, b_records in branch_buckets.items():
            ws_branch = wb.create_sheet(title=f"{b_name} Campus")
            populate_sheet(ws_branch, f"{b_name} Campus", b_records, f"{b_name} • {session_name}")
    else:
        # Single branch: Grouped by Course / Standard tabs
        for std_name, std_records in sorted(standard_buckets.items()):
            ws_std = wb.create_sheet(title=f"{std_name}")
            populate_sheet(ws_std, f"{std_name}", std_records, f"{branch_name} • {std_name}")

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output.getvalue()


def export_students_to_pdf(students_data, meta=None):
    """
    Generates an executive Landscape A4 PDF document matching the snapshot layout:
    - Left institutional title block with logo
    - Right scope & records metadata card
    - Amber accent line + Navy divider
    - Landscape table with Green paid fees and Red pending balances
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
        'StuHdrCenter',
        parent=styles['Normal'],
        fontName=FONT_FAMILY_BOLD,
        fontSize=7.5,
        leading=9.5,
        textColor=colors.white,
        alignment=1,
    )
    hdr_right_style = ParagraphStyle(
        'StuHdrRight',
        parent=styles['Normal'],
        fontName=FONT_FAMILY_BOLD,
        fontSize=7.5,
        leading=9.5,
        textColor=colors.white,
        alignment=2,
    )
    cell_normal = ParagraphStyle(
        'StuCellNormal',
        parent=styles['Normal'],
        fontName=FONT_FAMILY,
        fontSize=7,
        leading=9,
        textColor=colors.HexColor(COLOR_SLATE_TEXT),
    )
    cell_bold = ParagraphStyle(
        'StuCellBold',
        parent=styles['Normal'],
        fontName=FONT_FAMILY_BOLD,
        fontSize=7,
        leading=9,
        textColor=colors.HexColor(COLOR_SLATE_TEXT),
    )
    cell_center = ParagraphStyle(
        'StuCellCenter',
        parent=styles['Normal'],
        fontName=FONT_FAMILY,
        fontSize=7,
        leading=9,
        textColor=colors.HexColor(COLOR_SLATE_TEXT),
        alignment=1,
    )
    cell_right = ParagraphStyle(
        'StuCellRight',
        parent=styles['Normal'],
        fontName=FONT_FAMILY,
        fontSize=7,
        leading=9,
        textColor=colors.HexColor(COLOR_SLATE_TEXT),
        alignment=2,
    )
    cell_green_bold = ParagraphStyle(
        'StuCellGreen',
        parent=styles['Normal'],
        fontName=FONT_FAMILY_BOLD,
        fontSize=7,
        leading=9,
        textColor=colors.HexColor(COLOR_GREEN_PAID),
        alignment=2,
    )
    cell_red_bold = ParagraphStyle(
        'StuCellRed',
        parent=styles['Normal'],
        fontName=FONT_FAMILY_BOLD,
        fontSize=7,
        leading=9,
        textColor=colors.HexColor(COLOR_RED_PENDING),
        alignment=2,
    )

    story = []

    # 1. Executive Snapshot Header
    header_meta = {
        'institute_name': meta.get('institute_name', 'SUTAWANE CLASSES VAIJAPUR'),
        'branch_name': branch_name,
        'session_name': session_name,
        'branch_logo': meta.get('branch_logo'),
        'date_str': meta.get('date_str'),
        'records_count': len(students_data),
        'overall_pending_total': meta.get('overall_pending_total'),
        'session_pending_total': meta.get('session_pending_total'),
    }
    header_elements = build_executive_pdf_header(
        doc_title="STUDENTS ENROLLMENT & ACADEMIC DIRECTORY",
        meta=header_meta,
        report_badge_label="ENROLLMENTS:",
        report_badge_value=f"{len(students_data)} Students",
    )
    story.extend(header_elements)

    # 2. Table Headers
    tbl_headers = [
        Paragraph("#", hdr_style),
        Paragraph("Roll No.", hdr_style),
        Paragraph("Student Full Name", hdr_style),
        Paragraph("Class / Course", hdr_style),
        Paragraph("Campus Branch", hdr_style),
        Paragraph("Parent Contact", hdr_style),
        Paragraph("Agreed Fees (Rs.)", hdr_right_style),
        Paragraph("Paid Amount (Rs.)", hdr_right_style),
        Paragraph("Pending Dues (Rs.)", hdr_right_style),
        Paragraph("Fee Status", hdr_style),
        Paragraph("Enrollment", hdr_style),
    ]

    tbl_rows = [tbl_headers]

    tot_agreed = 0.0
    tot_paid = 0.0
    tot_pending = 0.0

    for idx, item in enumerate(students_data, 1):
        st = item.get('student')
        adm = item.get('admission')

        st_name = st.full_name if st else '—'
        roll_no = adm.roll_number if adm else '—'
        std_name = adm.standard if adm else '—'
        b_name = adm.branch.name if adm and adm.branch else '—'
        p_phone = st.parent_phone if st else '—'

        agreed = float(item.get('total_fees', 0.0))
        paid = float(item.get('paid_fees', 0.0))
        pending = float(item.get('pending_fees', 0.0))
        f_status = item.get('fee_status', 'PAID')
        is_active = "Active" if adm and adm.is_active else "Archived"

        tot_agreed += agreed
        tot_paid += paid
        tot_pending += pending

        # Status badge formatting
        status_color = "#16A34A" if f_status == 'PAID' else ("#F59E0B" if f_status == 'PARTIAL' else "#DC2626")
        status_html = f"<font color='{status_color}'><b>{f_status}</b></font>"

        row = [
            Paragraph(str(idx), cell_center),
            Paragraph(str(roll_no), cell_bold),
            Paragraph(str(st_name), cell_bold),
            Paragraph(str(std_name), cell_normal),
            Paragraph(str(b_name), cell_normal),
            Paragraph(str(p_phone), cell_center),
            Paragraph(format_currency_inr(agreed), cell_right),
            Paragraph(format_currency_inr(paid), cell_green_bold),
            Paragraph(format_currency_inr(pending), cell_red_bold if pending > 0 else cell_right),
            Paragraph(status_html, cell_center),
            Paragraph(is_active, cell_center),
        ]
        tbl_rows.append(row)

    # 3. Totals Row
    tbl_rows.append([
        Paragraph(f"<b>TOTAL ({len(students_data)} Students Enrolled)</b>", cell_bold),
        "", "", "", "", "",
        Paragraph(format_currency_inr(tot_agreed), cell_bold),
        Paragraph(format_currency_inr(tot_paid), cell_green_bold),
        Paragraph(format_currency_inr(tot_pending), cell_red_bold),
        "",
        "",
    ])

    # Col Widths totaling 802 pt (fits Landscape A4 printable width: 841.89 - 40 = 801.89)
    # [24, 60, 148, 80, 80, 80, 75, 75, 75, 55, 50] = 802
    col_widths = [24, 60, 148, 80, 80, 80, 75, 75, 75, 55, 50]
    data_table = Table(tbl_rows, colWidths=col_widths, repeatRows=1)
    data_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(COLOR_NAVY_SECONDARY)),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('GRID', (0, 0), (-1, -2), 0.5, colors.HexColor(COLOR_BORDER)),
        ('SPAN', (0, -1), (5, -1)),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor(COLOR_BG_TOTALS)),
        ('LINEABOVE', (0, -1), (-1, -1), 1.2, colors.HexColor(COLOR_NAVY_PRIMARY)),
        ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, colors.HexColor('#F8FAFC')]),
    ]))

    story.append(data_table)

    doc.build(story, canvasmaker=ExecutiveLandscapeCanvas)
    buffer.seek(0)
    return buffer.getvalue()
