"""
Export Theme & Design System for Sutawane Classes Management Software.
Provides shared styling, executive PDF header matching official institutional branding,
and automated Openpyxl Excel layout formatting with multi-sheet data isolation support.
"""

import os
import io
from datetime import datetime
from django.conf import settings
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter


# =============================================================================
# Unicode & Indian Rupee Typography Registration
# =============================================================================

HAS_UNICODE_FONT = False
FONT_FAMILY = 'Helvetica'
FONT_FAMILY_BOLD = 'Helvetica-Bold'

def _init_fonts():
    global HAS_UNICODE_FONT, FONT_FAMILY, FONT_FAMILY_BOLD
    if HAS_UNICODE_FONT:
        return
    
    candidates = []
    if os.name == 'nt':
        win_fonts = os.environ.get('WINDIR', 'C:\\Windows') + '\\Fonts'
        candidates.extend([
            ('SegoeUI', os.path.join(win_fonts, 'segoeui.ttf'), os.path.join(win_fonts, 'segoeuib.ttf')),
            ('Arial', os.path.join(win_fonts, 'arial.ttf'), os.path.join(win_fonts, 'arialbd.ttf')),
            ('Calibri', os.path.join(win_fonts, 'calibri.ttf'), os.path.join(win_fonts, 'calibrib.ttf')),
        ])
    else:
        # Common Linux font paths
        candidates.extend([
            ('DejaVuSans', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'),
            ('FreeSans', '/usr/share/fonts/truetype/freefont/FreeSans.ttf', '/usr/share/fonts/truetype/freefont/FreeSansBold.ttf'),
        ])

    for fname, f_reg, f_bld in candidates:
        if os.path.exists(f_reg) and os.path.exists(f_bld):
            try:
                pdfmetrics.registerFont(TTFont(fname, f_reg))
                pdfmetrics.registerFont(TTFont(f"{fname}-Bold", f_bld))
                FONT_FAMILY = fname
                FONT_FAMILY_BOLD = f"{fname}-Bold"
                HAS_UNICODE_FONT = True
                break
            except Exception:
                continue

_init_fonts()


# =============================================================================
# Brand Design Tokens & Colors
# =============================================================================

COLOR_NAVY_PRIMARY = '#1A2B4C'     # Executive Institutional Dark Navy
COLOR_NAVY_SECONDARY = '#28375C'   # Table Header Navy
COLOR_AMBER_ACCENT = '#F59E0B'     # Vibrant Accent Line & Badges
COLOR_GREEN_PAID = '#16A34A'       # Received Amounts / Paid Status
COLOR_RED_PENDING = '#DC2626'      # Due Amounts / Pending Balances
COLOR_SLATE_TEXT = '#1E293B'       # Standard Dark Text
COLOR_MUTED_TEXT = '#64748B'       # Subtitles & Labels
COLOR_BG_CARD = '#F8FAFC'          # Header Meta Card Fill
COLOR_BG_TOTALS = '#F1F5F9'        # Summary Totals Row Fill
COLOR_BORDER = '#CBD5E1'           # Clean Cell Borders


# =============================================================================
# Currency & Number Formatting Helpers
# =============================================================================

def format_currency_inr(val, prefix="Rs. "):
    """
    Formats numeric values into standard Indian currency with commas (e.g. Rs. 15,000).
    Uses 'Rs. ' by default to guarantee missing glyph black boxes (■) NEVER appear in printouts.
    """
    try:
        val = float(val or 0.0)
        neg = val < 0
        val = abs(val)
        s, *d = f"{val:.2f}".split(".")
        if len(s) > 3:
            r = s[-3:]
            l = s[:-3]
            chunks = []
            while len(l) > 2:
                chunks.append(l[-2:])
                l = l[:-2]
            if l:
                chunks.append(l)
            chunks.reverse()
            s = ",".join(chunks) + "," + r
        res = s if not d or d[0] == '00' else f"{s}.{d[0]}"
        sym = prefix if prefix is not None else "Rs. "
        return f"-{sym}{res}" if neg else f"{sym}{res}"
    except Exception:
        sym = prefix if prefix is not None else "Rs. "
        return f"{sym}{val}"


def format_number_inr(val):
    """Formats numeric values into standard Indian comma-separated number without symbol."""
    try:
        val = float(val or 0.0)
        neg = val < 0
        val = abs(val)
        s, *d = f"{val:.2f}".split(".")
        if len(s) > 3:
            r = s[-3:]
            l = s[:-3]
            chunks = []
            while len(l) > 2:
                chunks.append(l[-2:])
                l = l[:-2]
            if l:
                chunks.append(l)
            chunks.reverse()
            s = ",".join(chunks) + "," + r
        res = s if not d or d[0] == '00' else f"{s}.{d[0]}"
        return f"-{res}" if neg else res
    except Exception:
        return str(val)


def get_logo_path(branch_logo=None):
    """
    Returns absolute path to institutional icon/logo on disk.
    Priority:
    1. Explicit branch logo if provided
    2. Master logo from SystemSetting 'logo_url' (configured in Settings Page)
    3. Any uploaded logo in MEDIA_ROOT/photos (e.g. logo-master-*)
    4. App static images: apps/MyApp/static/images/logo-master.png
    5. App static images: apps/MyApp/static/images/icon.png
    6. App static images: apps/MyApp/static/images/favicon.png
    """
    # 1. Branch logo
    if branch_logo:
        clean_logo = str(branch_logo).strip()
        if clean_logo.startswith('/media/'):
            rel = clean_logo[len('/media/'):].replace('/', os.sep)
            p = os.path.join(settings.MEDIA_ROOT, rel)
            if os.path.exists(p):
                return p
        elif os.path.exists(clean_logo):
            return clean_logo

    # 2. Master logo from SystemSetting (Settings Page)
    try:
        from .models import SystemSetting
        sett = SystemSetting.objects.filter(key='logo_url').first()
        if sett and sett.value:
            clean_val = sett.value.strip()
            if clean_val.startswith('/media/'):
                rel = clean_val[len('/media/'):].replace('/', os.sep)
                p = os.path.join(settings.MEDIA_ROOT, rel)
                if os.path.exists(p):
                    return p
            elif os.path.isabs(clean_val) and os.path.exists(clean_val):
                return clean_val
    except Exception:
        pass

    # 3. Check MEDIA_ROOT/photos directory for uploaded logo
    photos_dir = os.path.join(settings.MEDIA_ROOT, 'photos')
    if os.path.exists(photos_dir):
        try:
            files = sorted(os.listdir(photos_dir), reverse=True)
            for f in files:
                if f.startswith('logo-master') and os.path.splitext(f)[1].lower() in ('.png', '.jpg', '.jpeg', '.webp'):
                    p = os.path.join(photos_dir, f)
                    if os.path.exists(p):
                        return p
            for f in files:
                if f.startswith('logo-branch') and os.path.splitext(f)[1].lower() in ('.png', '.jpg', '.jpeg', '.webp'):
                    p = os.path.join(photos_dir, f)
                    if os.path.exists(p):
                        return p
        except Exception:
            pass

    # 4. App static images in apps/MyApp/static/images
    app_static = os.path.join(settings.BASE_DIR, 'apps', 'MyApp', 'static', 'images')
    for name in ['logo-master.png', 'icon.png', 'favicon.png']:
        p = os.path.join(app_static, name)
        if os.path.exists(p):
            return p

    # 5. Global static directory
    for name in ['logo-master.png', 'icon.png', 'favicon.png']:
        p = os.path.join(settings.BASE_DIR, 'static', 'images', name)
        if os.path.exists(p):
            return p

    return None


# =============================================================================
# Two-Pass Page Numbering Canvas
# =============================================================================

class ExecutiveLandscapeCanvas(canvas.Canvas):
    """
    Two-pass canvas for ReportLab Landscape A4 PDFs.
    Draws professional running footer with 'Page X of Y' and institutional signature.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_footer(num_pages)
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)

    def draw_footer(self, page_count):
        self.saveState()
        self.setFont(FONT_FAMILY, 7.5)
        self.setFillColor(colors.HexColor(COLOR_MUTED_TEXT))
        page_w, page_h = landscape(A4)
        
        # Left footer: Institutional signature
        self.drawString(20, 14, "Sutawane Classes Management Software • Confidential Official Record")
        
        # Right footer: Page count
        self.drawRightString(page_w - 20, 14, f"Page {self._pageNumber} of {page_count}")
        
        # Thin divider line above footer
        self.setStrokeColor(colors.HexColor('#E2E8F0'))
        self.setLineWidth(0.5)
        self.line(20, 22, page_w - 20, 22)
        self.restoreState()


# =============================================================================
# Executive PDF Header Flowable Builder
# =============================================================================

def build_executive_pdf_header(doc_title, meta=None, report_badge_label=None, report_badge_value=None):
    """
    Constructs the exact executive header matching the official institutional layout:
    [ Logo ] [ Institute Name & Subtitle & Tagline ]   [ Scope & Date Box ]
    [====== Orange Accent Bar ======][============= Navy Line =============]
    """
    meta = meta or {}

    # Resolve institute name & tagline from SystemSetting if not provided
    institute_name = meta.get('institute_name')
    tagline = meta.get('tagline')
    if not institute_name or not tagline:
        try:
            from .models import SystemSetting
            settings_map = {s.key: s.value for s in SystemSetting.objects.all()}
            if not institute_name:
                institute_name = settings_map.get('institute_name') or 'Sutawane Classes'
            if not tagline:
                tagline = settings_map.get('tagline') or 'Excellence in Coaching & Board Preparations'
        except Exception:
            pass
    institute_name = (institute_name or 'SUTAWANE CLASSES').upper()
    tagline = tagline or 'Excellence in Coaching & Board Preparations'

    branch_name = meta.get('branch_name', 'All Branches')
    session_name = meta.get('session_name', 'All Sessions')
    date_str = meta.get('date_str') or datetime.now().strftime("%d %b %Y, %I:%M %p")
    records_count = meta.get('records_count')

    # Typography styles
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'HdrInstTitle',
        parent=styles['Normal'],
        fontName=FONT_FAMILY_BOLD,
        fontSize=13,
        leading=16,
        textColor=colors.HexColor(COLOR_NAVY_PRIMARY),
    )
    subtitle_style = ParagraphStyle(
        'HdrReportSub',
        parent=styles['Normal'],
        fontName=FONT_FAMILY_BOLD,
        fontSize=9.5,
        leading=12,
        textColor=colors.HexColor(COLOR_NAVY_PRIMARY),
    )
    tagline_style = ParagraphStyle(
        'HdrTagline',
        parent=styles['Normal'],
        fontName=FONT_FAMILY,
        fontSize=7.5,
        leading=10,
        textColor=colors.HexColor(COLOR_MUTED_TEXT),
    )
    meta_lbl_style = ParagraphStyle(
        'HdrMetaLbl',
        parent=styles['Normal'],
        fontName=FONT_FAMILY_BOLD,
        fontSize=7,
        leading=9,
        textColor=colors.HexColor(COLOR_MUTED_TEXT),
    )
    meta_val_style = ParagraphStyle(
        'HdrMetaVal',
        parent=styles['Normal'],
        fontName=FONT_FAMILY_BOLD,
        fontSize=7.5,
        leading=9,
        textColor=colors.HexColor(COLOR_SLATE_TEXT),
    )
    meta_val_red_style = ParagraphStyle(
        'HdrMetaValRed',
        parent=styles['Normal'],
        fontName=FONT_FAMILY_BOLD,
        fontSize=7.5,
        leading=9,
        textColor=colors.HexColor(COLOR_RED_PENDING),
    )

    # Left block: Title, Subtitle, Tagline
    left_flowables = [
        Paragraph(institute_name, title_style),
        Spacer(1, 2),
        Paragraph(doc_title.upper(), subtitle_style),
        Spacer(1, 2),
        Paragraph(tagline, tagline_style),
    ]

    # Right block: Scope Metadata Card Table (Use &bull; for crisp universal bullet)
    scope_display = f"{branch_name} &bull; {session_name}"
    
    badge_lbl = report_badge_label or "RECORDS:"
    if report_badge_value is not None:
        badge_val = report_badge_value
    elif records_count is not None:
        badge_val = f"{records_count} Students Pending" if "DUE" in doc_title.upper() else f"{records_count} Records Found"
    else:
        badge_val = "Verified"

    meta_rows = [
        [Paragraph("SCOPE:", meta_lbl_style), Paragraph(scope_display, meta_val_style)],
        [Paragraph("DATE:", meta_lbl_style), Paragraph(date_str, meta_val_style)],
    ]
    if meta.get('overall_pending_total') is not None:
        meta_rows.append([
            Paragraph("ALL SESSIONS DUE:", meta_lbl_style),
            Paragraph(format_currency_inr(meta.get('overall_pending_total')), meta_val_red_style)
        ])
    meta_rows.append([Paragraph(badge_lbl, meta_lbl_style), Paragraph(str(badge_val), meta_val_red_style)])

    meta_table = Table(meta_rows, colWidths=[70, 168])
    meta_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(COLOR_BG_CARD)),
        ('BOX', (0, 0), (-1, -1), 0.75, colors.HexColor(COLOR_BORDER)),
        ('TOPPADDING', (0, 0), (-1, -1), 2.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))

    # Assemble 3-column top header row
    logo_path = get_logo_path(branch_logo=meta.get('branch_logo') or meta.get('branch_logo_url'))
    if logo_path and os.path.exists(logo_path):
        try:
            logo_flowable = Image(logo_path, width=44, height=44, kind='proportional')
        except Exception:
            logo_flowable = Paragraph("<b>SC</b>", title_style)
    else:
        logo_flowable = Paragraph("<b>SC</b>", title_style)

    header_table = Table(
        [[logo_flowable, left_flowables, meta_table]],
        colWidths=[50, 514, 238]
    )
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))

    # Bottom accent divider line: 120pt Amber/Orange segment + remaining Navy segment
    accent_table = Table([['', '']], colWidths=[120, 682], rowHeights=[3])
    accent_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, 0), colors.HexColor(COLOR_AMBER_ACCENT)),
        ('BACKGROUND', (1, 0), (1, 0), colors.HexColor(COLOR_NAVY_PRIMARY)),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))

    return [
        header_table,
        Spacer(1, 4),
        accent_table,
        Spacer(1, 10),
    ]


# =============================================================================
# Automated Openpyxl Excel Formatting Engine
# =============================================================================

def format_excel_worksheet(ws, title_text, meta_text=None, header_row=4, total_rows_count=0):
    """
    Applies unified institutional Excel layout to an openpyxl Worksheet:
    - Title banner in Navy (#1A2B4C)
    - Metadata subtitle
    - Auto column widths with safe padding (+4 chars)
    - Standard row heights (Title=28, Meta=18, Headers=24, Rows=20)
    - Gridlines enabled
    """
    ws.views.sheetView[0].showGridLines = True

    # Styling fonts & fills
    title_font = Font(name="Calibri", size=14, bold=True, color="1A2B4C")
    meta_font = Font(name="Calibri", size=10, italic=True, color="64748B")
    hdr_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    navy_fill = PatternFill(start_color="28375C", end_color="28375C", fill_type="solid")

    max_col = ws.max_column or 1
    max_col_letter = get_column_letter(max_col)

    # 1. Title Block
    ws.merge_cells(f"A1:{max_col_letter}1")
    ws["A1"] = title_text
    ws["A1"].font = title_font
    ws["A1"].alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 28

    if meta_text:
        ws.merge_cells(f"A2:{max_col_letter}2")
        ws["A2"] = meta_text
        ws["A2"].font = meta_font
        ws["A2"].alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[2].height = 18

    ws.row_dimensions[3].height = 8  # Blank separator

    # 2. Header Row
    ws.row_dimensions[header_row].height = 24
    for col in range(1, max_col + 1):
        cell = ws.cell(row=header_row, column=col)
        cell.font = hdr_font
        cell.fill = navy_fill
        cell.alignment = Alignment(horizontal=cell.alignment.horizontal or "center", vertical="center")

    # 3. Auto-fit Column Widths
    for col in ws.columns:
        col_letter = get_column_letter(col[0].column)
        max_len = 0
        for cell in col:
            # Skip merged title rows 1 and 2 for width calculation
            if cell.row in (1, 2, 3):
                continue
            val_str = str(cell.value or '')
            if len(val_str) > max_len:
                max_len = len(val_str)
        ws.column_dimensions[col_letter].width = max(max_len + 4, 12)
