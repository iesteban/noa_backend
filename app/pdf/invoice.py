from __future__ import annotations

import io
from datetime import date

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.models.client import Client
from app.models.contractor import Contractor
from app.models.invoice import Invoice, InvoiceLine


def render_invoice_pdf(
    invoice: Invoice,
    contractor: Contractor,
    client: Client,
    lines: list[InvoiceLine],
) -> bytes:
    """Generate a SII-compatible invoice PDF and return the raw bytes."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )

    styles = getSampleStyleSheet()
    normal = styles["Normal"]
    heading = styles["Heading1"]

    elements = []

    # --- Header ---
    elements.append(Paragraph("FACTURA", heading))
    elements.append(Spacer(1, 0.3 * cm))

    # Contractor and invoice metadata side by side
    contractor_info = [
        f"<b>{contractor.business_name or contractor.name}</b>",
        f"NIF: {contractor.nif or '—'}",
    ]
    if contractor.iban:
        contractor_info.append(f"IBAN: {contractor.iban}")

    invoice_meta = [
        f"<b>Nº Factura:</b> {invoice.invoice_number}",
        f"<b>Fecha:</b> {_fmt_date(invoice.date)}",
    ]
    if invoice.due_date:
        invoice_meta.append(f"<b>Vencimiento:</b> {_fmt_date(invoice.due_date)}")

    header_data = [
        [
            "\n".join(contractor_info),
            "\n".join(invoice_meta),
        ]
    ]
    header_table = Table(header_data, colWidths=[9.5 * cm, 7 * cm])
    header_table.setStyle(
        TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
        ])
    )
    elements.append(header_table)
    elements.append(Spacer(1, 0.5 * cm))

    # --- Client block ---
    client_lines = [f"<b>Cliente:</b> {client.name}"]
    if client.nif:
        client_lines.append(f"NIF: {client.nif}")
    elements.append(Paragraph("<br/>".join(client_lines), normal))
    elements.append(Spacer(1, 0.5 * cm))

    # --- Line items table ---
    line_header = ["Descripción", "Cant.", "Precio unit.", "Total"]
    table_data = [line_header]
    for ln in lines:
        table_data.append([
            ln.description,
            f"{float(ln.quantity):.2f}",
            f"{float(ln.unit_price):.2f} €",
            f"{float(ln.line_total):.2f} €",
        ])

    col_widths = [9.5 * cm, 2 * cm, 3 * cm, 2 * cm]
    line_table = Table(table_data, colWidths=col_widths)
    line_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2C3E50")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8F9FA")]),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#DEE2E6")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ])
    )
    elements.append(line_table)
    elements.append(Spacer(1, 0.4 * cm))

    # --- Totals block (right-aligned) ---
    iva_pct = int(float(lines[0].iva_rate) * 100) if lines else 21
    irpf_pct = int(float(lines[0].irpf_rate) * 100) if lines else 15

    totals_data = [
        ["Base imponible", f"{float(invoice.subtotal):.2f} €"],
        [f"IVA ({iva_pct}%)", f"{float(invoice.iva_amount):.2f} €"],
        [f"IRPF (-{irpf_pct}%)", f"-{float(invoice.irpf_amount):.2f} €"],
        ["TOTAL", f"{float(invoice.total):.2f} €"],
    ]
    totals_table = Table(totals_data, colWidths=[4 * cm, 3 * cm], hAlign="RIGHT")
    totals_table.setStyle(
        TableStyle([
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ("LINEABOVE", (0, -1), (-1, -1), 1, colors.black),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, -1), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ])
    )
    elements.append(totals_table)

    doc.build(elements)
    return buf.getvalue()


def _fmt_date(d: date) -> str:
    return d.strftime("%d/%m/%Y")
