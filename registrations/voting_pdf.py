"""Public, contact-free PDF output from a sanitized calculation snapshot."""
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, LongTable, TableStyle, PageBreak


def report(name, result):
    root = Path(__file__).parent / "static/registrations/fonts"
    for font, filename in [("Disco", "DejaVuSans.ttf"), ("Disco-Bold", "DejaVuSans-Bold.ttf")]:
        if font not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(font, str(root / filename)))
    styles = getSampleStyleSheet()
    for style in styles.byName.values():
        style.fontName = "Disco"
    styles["Title"].fontName = styles["Heading2"].fontName = "Disco-Bold"
    styles["BodyText"].fontSize = 9
    styles["BodyText"].leading = 13
    output = BytesIO()
    doc = SimpleDocTemplate(output, pagesize=landscape(A4), rightMargin=28, leftMargin=28, topMargin=32, bottomMargin=32, title=name, author="DISCO UKRAÏNA")
    story = []
    p = lambda value: Paragraph(escape(str(value)), styles["BodyText"])
    def heading(value):
        story.extend([Spacer(1, 12), Paragraph(escape(value), styles["Heading2"])])
    def table(headers, rows, widths=None):
        data = [[p(v) for v in headers]] + [[p(v) for v in row] for row in rows]
        t = LongTable(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e1d5ed")), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("GRID", (0, 0), (-1, -1), .25, colors.HexColor("#c5c5cb")), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f4f8")]), ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6)]))
        story.append(t)
    story.append(Paragraph(escape(name), styles["Title"]))
    heading("Як відбувалося голосування")
    story.append(p("Глядачі голосували паперовими бюлетенями: один бюлетень — один гість — один голос за одного учасника. Втрачений бюлетень не замінювали. Недійсні бюлетені не враховано. Члени журі обирали трійку фаворитів: 5, 3 та 1 бал; усі інші отримували 0."))
    story.append(p("Загальний банк — 1000 балів: 750 від глядачів (75%) і 250 від журі (25%). Обидва банки розподілено пропорційно. Цілі бали отримано методом найбільших залишків, тому суми дорівнюють рівно 750 і 250. Місця визначено за точними значеннями до округлення. Голоси за дискваліфікованих збережено для історії, але вилучено з обох розрахункових баз; журі не перерозподіляло оцінки."))
    table(["Усього бюлетенів", "Недійсні", "Дійсні", "За дискваліфікованих", "У розрахунку", "Оцінки журі у розрахунку"], [[result[k] for k in ("total_ballots", "invalid_ballots", "valid_ballots", "excluded_votes", "eligible_votes", "eligible_jury")]])
    heading("Підсумкові результати")
    rows = result["rows"]
    table(["Місце", "№", "Ім’я", "Журі /250", "Глядачі /750", "Разом /1000", "Точний результат", "Статус / причина"], [[r["rank"] or "—", r["number"] or f"реєстр. {r['original']}", r["name"], r["jury_points"], r["audience_points"], r["total"], r["combined_exact"]["fraction"], r["status"] + (": " + r["reason"] if r["reason"] else "")] for r in rows], [42, 50, 120, 62, 75, 75, 110, 140])
    heading("Голоси глядачів — деталі")
    table(["№ / ім’я", "Голоси", "% врахованих", "Точні бали (дріб)", "Оголошені бали", "Статус"], [[f"{r['number'] or '—'} / {r['name']}", r["votes"], f"{float(r['audience_percent']):.4f}%", r["audience_exact"]["fraction"], r["audience_points"], r["status"]] for r in rows], [180, 70, 100, 150, 110, 164])
    heading("Журі — деталі")
    table(["№ / ім’я", "Оцінок 5 / 3 / 1", "Сума оцінок", "% врахованих", "Точні бали (дріб)", "Оголошені бали"], [[f"{r['number'] or '—'} / {r['name']}", f"{r['fives']} / {r['threes']} / {r['ones']}", r["jury_raw"], f"{float(r['jury_percent']):.4f}%", r["jury_exact"]["fraction"], r["jury_points"]] for r in rows], [180, 100, 95, 95, 180, 124])
    heading("Усі оцінки журі")
    # Horizontal chunks keep any number of jury members readable on A4.
    jury = result["jury"]
    for start in range(0, len(jury), 6):
        members = jury[start:start + 6]
        table(["№ / ім’я"] + [f"Журі {j['code']} — {j['name']}" for j in members], [[f"{r['number']} / {r['name']}"] + r["scores"][start:start + 6] for r in result["jury_table"]], [200] + [574 / len(members)] * len(members))
        story.append(Spacer(1, 10))
    heading("Перевірки та правила рівності")
    story.append(p("За однакових точних сум порівнюються: результат глядачів, кількість їхніх голосів, кількість оцінок журі 5, потім 3, потім 1. За повної рівності — спільне місце. Для останнього цілого бала за однакових залишків: у глядачів — більше голосів; у журі — більше оцінок 5 / 3 / 1; за повної рівності — реєстраційний порядок."))
    for notice in result["warnings"] + result["rounding_notices"]:
        story.append(p(notice))
    if not result["warnings"]:
        story.append(p("Тай-брейк для підсумкових місць не застосовувався."))
    def footer(canvas, document):
        canvas.setFont("Disco", 8)
        canvas.drawString(28, 17, "DISCO UKRAÏNA · Публічний звіт")
        canvas.drawRightString(814, 17, str(document.page))
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()
