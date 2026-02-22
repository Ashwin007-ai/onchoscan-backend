from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Image as RLImage,
    Table, TableStyle, HRFlowable, KeepTogether
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
import os, datetime, uuid


# ── Logo + header drawn on every page via canvas ──────────────────────────────
def _draw_page_header(canv, doc):
    """Paints the OnchoScan logo + brand at top-left of every page."""
    canv.saveState()
    W, H = letter
    cy = H - 0.45 * inch          # vertical centre of the logo row

    # ── Circle background ──
    canv.setFillColor(colors.HexColor("#050d15"))
    canv.circle(0.55 * inch, cy, 0.22 * inch, fill=1, stroke=0)

    # ── Green ring ──
    canv.setStrokeColor(colors.HexColor("#4fffb0"))
    canv.setLineWidth(1.5)
    canv.circle(0.55 * inch, cy, 0.22 * inch, fill=0, stroke=1)

    # ── Waveform inside circle ──
    canv.setLineWidth(1.2)
    p = canv.beginPath()
    p.moveTo(0.36 * inch, cy)
    p.curveTo(0.42 * inch, cy + 0.09 * inch,
              0.48 * inch, cy - 0.09 * inch,
              0.55 * inch, cy)
    p.curveTo(0.62 * inch, cy + 0.09 * inch,
              0.68 * inch, cy - 0.09 * inch,
              0.74 * inch, cy)
    canv.drawPath(p, stroke=1, fill=0)

    # ── Brand text ──
    canv.setFont("Helvetica-Bold", 11)
    canv.setFillColor(colors.HexColor("#0d1b2a"))
    canv.drawString(0.84 * inch, cy - 0.04 * inch, "OnchoScan")

    # ── Date on the right ──
    canv.setFont("Helvetica", 8)
    canv.setFillColor(colors.HexColor("#5c6b7d"))
    canv.drawRightString(W - 0.5 * inch, cy - 0.04 * inch,
                         datetime.datetime.now().strftime("%Y-%m-%d"))

    # ── Thin blue separator ──
    canv.setStrokeColor(colors.HexColor("#1a73e8"))
    canv.setLineWidth(1.0)
    canv.line(0.5 * inch, H - 0.68 * inch, W - 0.5 * inch, H - 0.68 * inch)

    canv.restoreState()


def generate_pdf_report(result_data, heatmap_path, original_path=None, patient_info=None):
    os.makedirs("reports", exist_ok=True)
    file_path = f"reports/report_{uuid.uuid4().hex}.pdf"

    doc = SimpleDocTemplate(
        file_path, pagesize=letter,
        topMargin    = 1.0 * inch,   # room for the canvas logo header
        bottomMargin = 0.75 * inch,
        leftMargin   = 0.65 * inch,
        rightMargin  = 0.65 * inch,
    )

    styles = getSampleStyleSheet()

    # ── Styles ────────────────────────────────────────────────────────────────
    title_style = ParagraphStyle("ReportTitle",
        fontName="Helvetica-Bold", fontSize=18,
        textColor=colors.HexColor("#0d1b2a"),
        alignment=TA_CENTER, spaceAfter=3, spaceBefore=0)

    subtitle_style = ParagraphStyle("ReportSub",
        fontName="Helvetica", fontSize=10,
        textColor=colors.HexColor("#5c6b7d"),
        alignment=TA_CENTER, spaceAfter=14, spaceBefore=0)

    heading_style = ParagraphStyle("H2",
        fontName="Helvetica-Bold", fontSize=12,
        textColor=colors.HexColor("#0d1b2a"),
        spaceBefore=14, spaceAfter=6)

    body_style = ParagraphStyle("Body",
        fontName="Helvetica", fontSize=10,
        textColor=colors.HexColor("#2d3748"), leading=16)

    note_label_style = ParagraphStyle("NoteLabel",
        fontName="Helvetica-Bold", fontSize=10,
        textColor=colors.HexColor("#1a73e8"),
        spaceBefore=8, spaceAfter=5)

    note_body_style = ParagraphStyle("NoteBody",
        fontName="Helvetica", fontSize=10,
        textColor=colors.HexColor("#2d3748"), leading=15)

    story = []

    # ── Report title block  (NOT the logo — that is drawn by canvas) ──────────
    story.append(Spacer(1, 4))
    story.append(Paragraph("Multi-Cancer Diagnostic Report", title_style))
    story.append(Paragraph("AI-Assisted Screening · ResNet-18 + Grad-CAM", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=1.2,
                             color=colors.HexColor("#1a73e8"), spaceAfter=12))

    # ── Meta row ─────────────────────────────────────────────────────────────
    meta_rows = [
        ["Generated:", datetime.datetime.now().strftime("%Y-%m-%d  %H:%M:%S")],
        ["Cancer Type:", result_data.get("cancer_type", "").title()],
        ["Report ID:",   str(uuid.uuid4())[:8].upper()],
    ]
    meta_tbl = Table(meta_rows, colWidths=[1.5*inch, 5.0*inch])
    meta_tbl.setStyle(TableStyle([
        ("FONTNAME",  (0,0), (-1,-1), "Helvetica"),
        ("FONTNAME",  (0,0), (0,-1),  "Helvetica-Bold"),
        ("FONTSIZE",  (0,0), (-1,-1), 10),
        ("TEXTCOLOR", (0,0), (-1,-1), colors.HexColor("#2d3748")),
        ("ROWBACKGROUNDS", (0,0), (-1,-1), [colors.HexColor("#f8fafc"), colors.white]),
        ("TOPPADDING",    (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING",   (0,0), (-1,-1), 8),
    ]))
    story.append(meta_tbl)
    story.append(Spacer(1, 14))

    # ── Patient Information ───────────────────────────────────────────────────
    pi = patient_info or {}
    has_info = any([pi.get("patient_name"), pi.get("patient_age"), pi.get("patient_sex"),
                    pi.get("patient_symptoms"), pi.get("patient_note")])

    if has_info:
        story.append(Paragraph("Patient Information", heading_style))

        info_rows = []
        if pi.get("patient_name"):     info_rows.append(["Patient Name:", pi["patient_name"]])
        if pi.get("patient_age"):      info_rows.append(["Age:",          pi["patient_age"] + " years"])
        if pi.get("patient_sex"):      info_rows.append(["Sex:",          pi["patient_sex"]])
        if pi.get("patient_symptoms"): info_rows.append(["Symptoms:",     pi["patient_symptoms"]])

        if info_rows:
            pt = Table(info_rows, colWidths=[1.5*inch, 5.0*inch])
            pt.setStyle(TableStyle([
                ("FONTNAME",  (0,0), (-1,-1), "Helvetica"),
                ("FONTNAME",  (0,0), (0,-1),  "Helvetica-Bold"),
                ("FONTSIZE",  (0,0), (-1,-1), 10),
                ("TEXTCOLOR", (0,0), (-1,-1), colors.HexColor("#2d3748")),
                ("ROWBACKGROUNDS", (0,0), (-1,-1),
                 [colors.HexColor("#f0f7ff"), colors.white]),
                ("TOPPADDING",    (0,0), (-1,-1), 5),
                ("BOTTOMPADDING", (0,0), (-1,-1), 5),
                ("LEFTPADDING",   (0,0), (-1,-1), 8),
            ]))
            story.append(pt)

        # ── Clinical Notes — label THEN bordered box, kept together ──────────
        if pi.get("patient_note"):
            note_text = pi["patient_note"].replace("\n", "<br/>")

            # Wrap the note text inside a single-cell table to get the border box
            note_para  = Paragraph(note_text, note_body_style)
            note_table = Table([[note_para]],
                               colWidths=[doc.width])
            note_table.setStyle(TableStyle([
                ("BOX",           (0,0), (-1,-1), 1.2, colors.HexColor("#1a73e8")),
                ("BACKGROUND",    (0,0), (-1,-1), colors.HexColor("#f0f7ff")),
                ("TOPPADDING",    (0,0), (-1,-1), 10),
                ("BOTTOMPADDING", (0,0), (-1,-1), 10),
                ("LEFTPADDING",   (0,0), (-1,-1), 12),
                ("RIGHTPADDING",  (0,0), (-1,-1), 12),
            ]))

            # KeepTogether prevents the label splitting from its box across pages
            story.append(KeepTogether([
                Paragraph("Clinical Notes:", note_label_style),
                note_table,
            ]))

        story.append(Spacer(1, 10))

    # ── Prediction Summary ────────────────────────────────────────────────────
    story.append(Paragraph("Prediction Summary", heading_style))
    risk_color = {
        "High Risk":   "#c0392b",
        "Medium Risk": "#e67e22",
        "Low Risk":    "#27ae60",
    }.get(result_data.get("risk_level", ""), "#2d3748")

    summary_data = [
        ["Prediction", "Confidence", "Risk Score", "Risk Level"],
        [
            result_data.get("prediction", "").title(),
            f"{result_data.get('confidence', 0)}%",
            f"{result_data.get('risk_score', 0)} / 100",
            result_data.get("risk_level", ""),
        ],
    ]
    s_tbl = Table(summary_data, colWidths=[1.7*inch, 1.5*inch, 1.5*inch, 1.8*inch])
    s_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,0),  colors.HexColor("#0d1b2a")),
        ("TEXTCOLOR",     (0,0), (-1,0),  colors.white),
        ("FONTNAME",      (0,0), (-1,0),  "Helvetica-Bold"),
        ("FONTNAME",      (0,1), (-1,-1), "Helvetica"),
        ("FONTSIZE",      (0,0), (-1,-1), 10),
        ("ALIGN",         (0,0), (-1,-1), "CENTER"),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [colors.HexColor("#eef2ff")]),
        ("TOPPADDING",    (0,0), (-1,-1), 8),
        ("BOTTOMPADDING", (0,0), (-1,-1), 8),
        ("GRID",          (0,0), (-1,-1), 0.5, colors.HexColor("#cbd5e0")),
        ("TEXTCOLOR",     (3,1), (3,1),   colors.HexColor(risk_color)),
        ("FONTNAME",      (3,1), (3,1),   "Helvetica-Bold"),
    ]))
    story.append(s_tbl)
    story.append(Spacer(1, 10))

    # ── Diagnostic Summary ────────────────────────────────────────────────────
    story.append(Paragraph("Diagnostic Summary", heading_style))
    clean = (result_data.get("diagnostic_text", "")
             .replace("<strong>", "").replace("</strong>", ""))
    story.append(Paragraph(clean, body_style))

    # ── Recommendations ───────────────────────────────────────────────────────
    if result_data.get("suggestions"):
        story.append(Paragraph("Clinical Recommendations", heading_style))
        for i, s in enumerate(result_data["suggestions"], 1):
            story.append(Paragraph(f"{i}. {s}", body_style))
    story.append(Spacer(1, 14))

    # ── Grad-CAM images ───────────────────────────────────────────────────────
    if original_path and os.path.exists(original_path) and os.path.exists(heatmap_path):
        story.append(Paragraph("Explainable AI Visualization (Grad-CAM)", heading_style))
        lbl_tbl = Table([["Original Image", "Grad-CAM Heatmap"]],
                        colWidths=[3.2*inch, 3.2*inch])
        lbl_tbl.setStyle(TableStyle([
            ("FONTNAME",      (0,0), (-1,-1), "Helvetica-Bold"),
            ("FONTSIZE",      (0,0), (-1,-1), 9),
            ("ALIGN",         (0,0), (-1,-1), "CENTER"),
            ("TEXTCOLOR",     (0,0), (-1,-1), colors.HexColor("#5c6b7d")),
            ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ]))
        img_tbl = Table(
            [[RLImage(original_path, width=2.8*inch, height=2.8*inch),
              RLImage(heatmap_path,  width=2.8*inch, height=2.8*inch)]],
            colWidths=[3.2*inch, 3.2*inch]
        )
        img_tbl.setStyle(TableStyle([
            ("ALIGN",  (0,0), (-1,-1), "CENTER"),
            ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ]))
        story.append(lbl_tbl)
        story.append(img_tbl)
    elif os.path.exists(heatmap_path):
        story.append(Paragraph("Explainable AI Visualization (Grad-CAM)", heading_style))
        story.append(RLImage(heatmap_path, width=3*inch, height=3*inch))

    story.append(Spacer(1, 16))

    # ── Disclaimer ────────────────────────────────────────────────────────────
    story.append(HRFlowable(width="100%", thickness=1,
                             color=colors.HexColor("#cbd5e0"), spaceAfter=8))
    story.append(Paragraph(
        "Disclaimer: This report is generated by an AI-assisted screening tool and is NOT a "
        "substitute for professional medical diagnosis. Always consult a qualified healthcare "
        "professional for clinical evaluation and treatment.",
        ParagraphStyle("Disclaimer",
            fontName="Helvetica-Oblique", fontSize=8,
            textColor=colors.HexColor("#718096"), leading=12)
    ))

    doc.build(story,
              onFirstPage=_draw_page_header,
              onLaterPages=_draw_page_header)
    return file_path