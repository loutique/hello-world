"""Ukrainian presenter templates driven solely by verified competition results."""
from fractions import Fraction

INTRO = """А тепер — результати.

Щоб усе було зрозуміло, коротко пояснимо, як ми сьогодні рахуємо голоси.

У нас є 1 000 балів.

750 балів — це голоси глядачів. Ми порахували всі дійсні бюлетені й розподілили ці 750 балів пропорційно до кількості голосів за кожного учасника.

Ще 250 балів — від журі. Кожен член журі обрав свою трійку фаворитів: 5 балів за перше місце, 3 — за друге і 1 — за третє.

Спочатку подивимось на результат журі.

А потім почнемо додавати ваші 750 балів — і побачимо, хто сьогодні переможе."""


def script(result):
    rows = {r["id"]: r for r in result["rows"] if r["eligible"]}
    order = result["reveal_order"]
    jury_order = list(reversed(order))
    jury_rank = {cid: 1 + sum(rows[other]["jury_raw"] > rows[cid]["jury_raw"] for other in rows) for cid in rows}
    audience_rank = {cid: 1 + sum(rows[other]["votes"] > rows[cid]["votes"] for other in rows) for cid in rows}
    current = {cid: Fraction(r["jury_exact"]["fraction"]) for cid, r in rows.items()}
    # Use the same exact tie criteria as final ranking, never announced integer totals.
    def standings():
        return sorted(rows, key=lambda cid: (-current[cid], -Fraction(rows[cid]["audience_exact"]["fraction"]), -rows[cid]["votes"], -rows[cid]["fives"], -rows[cid]["threes"], -rows[cid]["ones"], rows[cid]["original"]))
    blocks = []
    remaining_bank = Fraction(750)
    for i, cid in enumerate(order):
        r = rows[cid]
        before = standings()
        leader = before[0]
        before_rank = before.index(cid) + 1
        old_top = set(before[:3])
        notes, spoken, states = [], [], []
        remaining = len(order) - i
        if remaining == 1:
            notes.append("ПАУЗА — ОСТАННІЙ РЕЗУЛЬТАТ")
            states.append("LAST_RESULT")
        elif remaining <= 3:
            notes.append("ПАУЗА — ОСТАННІ ТРИ")
            states.append("LAST_3")
        if cid != leader:
            if current[cid] + remaining_bank < current[leader]:
                states.append("CANNOT_CATCH_LEADER")
            elif current[cid] + remaining_bank > current[leader]:
                states.append("CAN_TAKE_LEAD")
                if remaining <= 3:
                    spoken.append("Ще є можливість змінити лідера.")
        current[cid] += Fraction(r["audience_exact"]["fraction"])
        remaining_bank -= Fraction(r["audience_exact"]["fraction"])
        after = standings()
        notes.append("ПАУЗА" if remaining <= 3 else "ШВИДКО")
        spoken.append(f"Учасник №{r['number']} — {r['name']}.\nВід журі — {r['jury_points']} балів.\nВід глядачів — {r['audience_points']}.\nРазом — {r['total']} балів.")
        if after[0] == cid and leader != cid and current[cid] > current[leader]:
            states.append("NEW_LEADER")
            notes.append("НОВИЙ ЛІДЕР")
            spoken.append("Маємо нового лідера!")
        new_rank = after.index(cid) + 1
        if before_rank - new_rank >= 3:
            states.append("BIG_JUMP")
            spoken.append(f"Підйом одразу на {before_rank - new_rank} позиції — тепер це {new_rank}-те місце у поточній таблиці!")
        if cid not in old_top and cid in after[:3] and len(rows) > 3:
            states.append("ENTERS_TOP_3")
            notes.append("ТОП-3")
            displaced = old_top - set(after[:3])
            spoken.append("Цей результат виводить учасника до поточної трійки лідерів.")
            if displaced:
                notes.append("З ТОП-3 ВИБУВАЄ: " + ", ".join(rows[x]["name"] for x in displaced))
        if len(rows) >= 6 and max(r["votes"] for r in rows.values()) > min(r["votes"] for r in rows.values()) and abs(jury_rank[cid] - audience_rank[cid]) >= (len(rows) + 1) // 2:
            spoken.append("Тут уподобання глядачів і журі помітно розійшлися.")
        blocks.append({"states": states or ["NORMAL"], "notes": notes, "spoken": "\n\n".join(spoken), "remaining": remaining - 1, "id": cid})
    winners = [r for r in result["rows"] if r["rank"] == 1]
    ending = "Перемогу здобуває " + ", ".join(f"№{r['number']} — {r['name']}" for r in winners) + ". Вітаємо!"
    if len(winners) > 1:
        ending = "Перше місце ділять " + ", ".join(f"№{r['number']} — {r['name']}" for r in winners) + ". Вітаємо!"
    return {"intro": INTRO, "blocks": blocks, "ending": ending,
        "jury_results": [rows[cid] for cid in jury_order], "warnings": result["warnings"]}
