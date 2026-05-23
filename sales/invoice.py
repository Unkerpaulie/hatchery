"""Invoice PDF generation for closed Sales.

Call ``generate_invoice(sale)`` to receive raw PDF bytes ready for an
HttpResponse.  All business constants (company name, footer text, VAT rate)
live here so they can be updated in one place without touching views or
templates.
"""

from decimal import Decimal
from io import BytesIO

from django.conf import settings

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT  # noqa: F401
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable, Image, Paragraph, SimpleDocTemplate, Spacer, Table,
    TableStyle,
)

# ── Font registration ─────────────────────────────────────────────────────────
_FONT_DIR = settings.BASE_DIR / "static" / "fonts"
pdfmetrics.registerFont(TTFont(
    "CormorantGaramond-SemiBoldItalic",
    str(_FONT_DIR / "CormorantGaramond-SemiBoldItalic.ttf"),
))
pdfmetrics.registerFont(TTFont(
    "CormorantGaramond-BoldItalic",
    str(_FONT_DIR / "CormorantGaramond-BoldItalic.ttf"),
))

# ── Business constants ──────────────────────────────────────────────────────
COMPANY_NAME   = "ROSA Eggsellent Poultry Farm"
FOOTER_ADDRESS = "Main Road, Mason Hall, Tobago"
FOOTER_PHONE   = "1 868 320-5484"
FOOTER_EMAIL   = "rosa4poultryfarm@gmail.com"
FOOTER_WEBSITE = "www.rosaeggsellentfarm.com"
FOOTER_THANKS  = "THANK YOU FOR YOUR BUSINESS!!"
PAYMENT_TERMS  = (
    "Payment is due within 30 days from the date of invoice unless otherwise "
    "agreed in writing. We accept the following forms of payment: "
    "Bank Transfer and Cash payment."
)
VAT_RATE = Decimal("0.125")  # 12.5 %

LOGO_PATH = str(settings.BASE_DIR / "static" / "img" / "Rosa_logo.jpg")

# ── Page geometry ───────────────────────────────────────────────────────────
PAGE_W, PAGE_H = A4
L_MARGIN = R_MARGIN = 15 * mm   # ≈ 0.59 in
T_MARGIN = 15 * mm              # ≈ 0.59 in
B_MARGIN = 26 * mm              # canvas footer rule sits at 22 mm; keep 4 mm clearance
CONTENT_W = PAGE_W - L_MARGIN - R_MARGIN

# ── Brand colours ────────────────────────────────────────────────────────────
GREEN       = colors.HexColor("#1a6b2e")
LIGHT_GREEN = colors.HexColor("#eaf4ec")
GREY        = colors.HexColor("#888888")
RULE_GREY   = colors.HexColor("#cccccc")


# ── Paragraph styles ─────────────────────────────────────────────────────────
def _make_styles():
    return {
        "co_name":    ParagraphStyle("co_name",    fontName="CormorantGaramond-BoldItalic",
                                     fontSize=25, leading=30, textColor=colors.black),
        "inv_title":  ParagraphStyle("inv_title",  fontName="Helvetica-Bold", fontSize=24,
                                     leading=28, textColor=GREEN, alignment=TA_RIGHT),
        "bill_label": ParagraphStyle("bill_label", fontName="Helvetica-Bold", fontSize=8,
                                     leading=10, textColor=GREEN),
        "cust_name":  ParagraphStyle("cust_name",  fontName="Helvetica-Bold", fontSize=10,
                                     leading=13),
        "cust_dtl":   ParagraphStyle("cust_dtl",   fontName="Helvetica",      fontSize=9,
                                     leading=12),
        "meta_lbl":   ParagraphStyle("meta_lbl",   fontName="Helvetica-Bold", fontSize=9,
                                     leading=12, alignment=TA_RIGHT),
        "meta_val":   ParagraphStyle("meta_val",   fontName="Helvetica",      fontSize=9,
                                     leading=12, alignment=TA_LEFT),
        "th":         ParagraphStyle("th",         fontName="Helvetica-Bold", fontSize=9,
                                     leading=11, textColor=colors.white),
        "th_r":       ParagraphStyle("th_r",       fontName="Helvetica-Bold", fontSize=9,
                                     leading=11, textColor=colors.white, alignment=TA_RIGHT),
        "td":         ParagraphStyle("td",         fontName="Helvetica",      fontSize=9,
                                     leading=12),
        "td_r":       ParagraphStyle("td_r",       fontName="Helvetica",      fontSize=9,
                                     leading=12, alignment=TA_RIGHT),
        "tot_lbl":    ParagraphStyle("tot_lbl",    fontName="Helvetica-Bold", fontSize=9,
                                     leading=12, alignment=TA_RIGHT),
        "tot_val":    ParagraphStyle("tot_val",    fontName="Helvetica",      fontSize=9,
                                     leading=12, alignment=TA_RIGHT),
        "grand_lbl":  ParagraphStyle("grand_lbl",  fontName="Helvetica-Bold", fontSize=10,
                                     leading=13, alignment=TA_RIGHT),
        "grand_val":  ParagraphStyle("grand_val",  fontName="Helvetica-Bold", fontSize=10,
                                     leading=13, alignment=TA_RIGHT),
        "terms":      ParagraphStyle("terms",      fontName="Helvetica",      fontSize=8,
                                     leading=11),
    }


# ── Footer (canvas-level, absolute-positioned) ───────────────────────────────
def _draw_footer(canvas, doc):
    canvas.saveState()
    y_rule = 22 * mm
    canvas.setStrokeColor(RULE_GREY)
    canvas.setLineWidth(0.5)
    canvas.line(L_MARGIN, y_rule, PAGE_W - R_MARGIN, y_rule)

    addr_line = (
        f"Address: {FOOTER_ADDRESS}     "
        f"Phone: {FOOTER_PHONE}     "
        f"Email: {FOOTER_EMAIL}     "
        f"Website: {FOOTER_WEBSITE}"
    )
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(colors.black)
    canvas.drawCentredString(PAGE_W / 2, 15 * mm, addr_line)

    canvas.setFont("Helvetica-Bold", 8)
    canvas.setFillColor(GREEN)
    canvas.drawCentredString(PAGE_W / 2, 9 * mm, FOOTER_THANKS)
    canvas.restoreState()


# ── Main entry point ─────────────────────────────────────────────────────────
def generate_invoice(sale) -> bytes:
    """Return raw PDF bytes for the given closed Sale."""
    S = _make_styles()
    buf = BytesIO()

    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=L_MARGIN, rightMargin=R_MARGIN,
        topMargin=T_MARGIN,  bottomMargin=B_MARGIN,
        title=f"Invoice #{sale.pk}", author=COMPANY_NAME,
    )

    story = []

    # ── Header ───────────────────────────────────────────────────────────────
    # Row 1: logo (left) + INVOICE label (right)
    # Row 2: company name spanning full width
    try:
        logo = Image(LOGO_PATH, width=56 * mm, height=56 * mm, kind="proportional")
    except Exception:
        logo = Spacer(56 * mm, 56 * mm)

    hdr = Table(
        [
            [logo, Paragraph("INVOICE", S["inv_title"])],
            [Paragraph(COMPANY_NAME, S["co_name"]), ""],
        ],
        colWidths=[CONTENT_W * 0.5, CONTENT_W * 0.5],
    )
    hdr.setStyle(TableStyle([
        ("SPAN",          (0, 1), (-1, 1)),   # company name spans full width on row 2
        ("VALIGN",        (0, 0), (-1, 0),  "MIDDLE"),
        ("VALIGN",        (0, 1), (-1, 1),  "TOP"),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        # Give the company name row breathing room so it doesn't crowd the HR below
        ("LEFTPADDING",   (0, 1), (-1, 1),  4),
        ("BOTTOMPADDING", (0, 1), (-1, 1),  10),
    ]))
    story.append(hdr)
    story.append(HRFlowable(width="100%", thickness=1, color=GREEN, spaceAfter=6))

    # ── Bill-To / Invoice meta ────────────────────────────────────────────────
    customer = sale.customer

    # Left cell: dynamic customer fields — skip any that are blank
    bill_parts = [Paragraph("BILL TO:", S["bill_label"])]
    if customer.name:
        bill_parts.append(Paragraph(customer.name, S["cust_name"]))
    if customer.address:
        safe = (customer.address
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace("\n", "<br/>"))
        bill_parts.append(Paragraph(safe, S["cust_dtl"]))
    if customer.phone_1:
        bill_parts.append(Paragraph(customer.phone_1, S["cust_dtl"]))
    if customer.email:
        bill_parts.append(Paragraph(customer.email, S["cust_dtl"]))

    # Right cell: invoice number and date
    date_str = f"{sale.date.day} {sale.date.strftime('%b %Y')}"
    meta = Table(
        [
            [Paragraph("Invoice #:", S["meta_lbl"]), Paragraph(f"{sale.pk:04d}", S["meta_val"])],
            [Paragraph("Date:",      S["meta_lbl"]), Paragraph(date_str,     S["meta_val"])],
        ],
        colWidths=[26 * mm, 30 * mm],
    )
    meta.setStyle(TableStyle([
        ("TOPPADDING",    (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))

    bill_tbl = Table([[bill_parts, meta]], colWidths=[CONTENT_W * 0.55, CONTENT_W * 0.45])
    bill_tbl.setStyle(TableStyle([
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("ALIGN",         (1, 0), (1,  0),  "RIGHT"),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(bill_tbl)
    story.append(Spacer(1, 8 * mm))

    # ── Line items + totals — single unified table ────────────────────────────
    # Column layout: QTY (20mm) | DESCRIPTION (flex) | UNIT PRICE (30mm) | TOTAL (30mm)
    col_w = [20 * mm, CONTENT_W - 20 * mm - 30 * mm - 30 * mm, 30 * mm, 30 * mm]

    # Header row
    rows = [[
        Paragraph("QTY",         S["th"]),
        Paragraph("DESCRIPTION", S["th"]),
        Paragraph("UNIT PRICE",  S["th_r"]),
        Paragraph("TOTAL",       S["th_r"]),
    ]]

    # Data rows
    lines = list(sale.lines.select_related("batch").all())
    for line in lines:
        breed = (line.batch.breed or "").strip()
        desc  = f"Chicks [{breed}]" if breed else "Chicks"
        rows.append([
            Paragraph(str(line.quantity),         S["td_r"]),
            Paragraph(desc,                        S["td"]),
            Paragraph(f"${line.unit_price:,.2f}", S["td_r"]),
            Paragraph(f"${line.line_total:,.2f}", S["td_r"]),
        ])

    # First totals row index (1 header + N data rows)
    r0 = len(rows)

    # Compute totals
    subtotal = sale.total_revenue
    vat      = (subtotal * VAT_RATE).quantize(Decimal("0.01"))
    total    = subtotal + vat

    # Three totals rows: cols 0-1 will be spanned for payment terms;
    # cols 2-3 carry the labels and values, naturally aligned with the columns above.
    rows.append([Paragraph(PAYMENT_TERMS, S["terms"]),
                 "",
                 Paragraph("SUBTOTAL",    S["tot_lbl"]),
                 Paragraph(f"${subtotal:,.2f}", S["tot_val"])])
    rows.append(["", "",
                 Paragraph("VAT (12.5%)", S["tot_lbl"]),
                 Paragraph(f"${vat:,.2f}",     S["tot_val"])])
    rows.append(["", "",
                 Paragraph("TOTAL DUE",  S["grand_lbl"]),
                 Paragraph(f"${total:,.2f}",   S["grand_val"])])

    # Build style commands
    ts = [
        # Header row styling
        ("BACKGROUND",    (0, 0),    (-1, 0),    GREEN),
        # Consistent grid across the whole table
        ("GRID",          (0, 0),    (-1, -1),   0.4, RULE_GREY),
        # Uniform cell padding
        ("TOPPADDING",    (0, 0),    (-1, -1),   5),
        ("BOTTOMPADDING", (0, 0),    (-1, -1),   5),
        ("LEFTPADDING",   (0, 0),    (-1, -1),   6),
        ("RIGHTPADDING",  (0, 0),    (-1, -1),   6),
        # QTY column centered in data rows only
        ("ALIGN",         (0, 1),    (0, r0 - 1), "CENTER"),
        # Unit price + total columns right-aligned throughout
        ("ALIGN",         (2, 0),    (3, -1),    "RIGHT"),
        # Payment terms: merge cols 0-1 across all three totals rows
        ("SPAN",          (0, r0),   (1, r0 + 2)),
        ("VALIGN",        (0, r0),   (0, r0),    "TOP"),
        # White background for the whole totals section
        ("BACKGROUND",    (0, r0),   (-1, r0 + 2), colors.white),
        # Green rule separating data rows from totals section
        ("LINEABOVE",     (0, r0),   (-1, r0),   1, GREEN),
        # Green rule above TOTAL DUE, only in the label+value columns
        ("LINEABOVE",     (2, r0+2), (3, r0+2),  1, GREEN),
        # Tighten vertical padding on the totals label/value rows
        ("TOPPADDING",    (2, r0),   (3, r0+2),  4),
        ("BOTTOMPADDING", (2, r0),   (3, r0+2),  4),
    ]

    # Alternating light-green shading on even data rows (skips header and totals)
    for i in range(2, r0, 2):
        ts.append(("BACKGROUND", (0, i), (-1, i), LIGHT_GREEN))

    tbl = Table(rows, colWidths=col_w, repeatRows=1)
    tbl.setStyle(TableStyle(ts))
    story.append(tbl)

    doc.build(story, onFirstPage=_draw_footer, onLaterPages=_draw_footer)
    return buf.getvalue()
