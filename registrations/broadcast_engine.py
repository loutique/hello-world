"""Reveal only information that has reached the persisted show position."""
from fractions import Fraction


def jury_top_count(result):
    return min(5, len(result["reveal_order"]))


def audience_start(result, flow_version=2):
    return 4 + jury_top_count(result) * 2 if flow_version >= 2 else 2 + jury_top_count(result)


def results_position(result, flow_version=2):
    return audience_start(result, flow_version) + 3 * len(result["reveal_order"])


def podium_places(result):
    return sorted({r["rank"] for r in result["rows"] if r["eligible"] and r["rank"] in (1, 2, 3)}, reverse=True)


def last_position(result, flow_version=2):
    return results_position(result, flow_version) + len(podium_places(result)) + 1


def public_frame(broadcast):
    result = broadcast.snapshot
    rows = {r["id"]: r for r in result["rows"] if r["eligible"]}
    order = result["reveal_order"]
    jury_order = list(reversed(order))
    top_count = jury_top_count(result)
    flow_version = getattr(broadcast, "flow_version", 2)
    start = audience_start(result, flow_version)
    position = min(broadcast.position, last_position(result, flow_version))
    frame = {"title": broadcast.title, "theme": broadcast.theme, "revision": broadcast.revision,
        "position": position, "last": last_position(result, flow_version), "count": len(order), "revealed": 0,
        "scene": "welcome", "board": [], "current": None, "winners": [], "notices": [], "headline": "", "top_count": top_count, "awardees": [], "award_place": None, "jury_points": None, "jury_sequence": None, "stage_label": "ОГОЛОШЕННЯ РЕЗУЛЬТАТІВ", "context": ""}
    if position == 0:
        return frame
    if flow_version >= 2 and position in {1, start - 1}:
        if position == 1:
            frame.update(scene="jury_intro", headline="Починаємо з рішення журі", stage_label="ЖУРІ · ЯК ОГОЛОШУЄМО",
                context="Зараз на екрані з’являться учасники з нижчими оцінками журі. Потім — п’ятірка лідерів, кожен окремо." if len(order) > 5 else "Зараз оголосимо рішення журі: спочатку побачимо бали, а наступним кроком дізнаємося, хто їх отримав.")
        else:
            frame.update(scene="audience_intro", headline="Тепер — голоси глядачів", stage_label="ГЛЯДАЧІ · НОВИЙ ЕТАП",
                context="Почнемо з учасника з найменшою кількістю балів журі. Далі — за початковою таблицею журі, від останньої позиції до першої.")
        return frame
    shown = set()
    known_jury = set(rows)
    jury_group = 2 if flow_version >= 2 else 1
    jury_start = jury_group + 1
    if position == jury_group:
        frame["scene"] = "jury"
        known_jury = set(jury_order[top_count:])
    elif position < start:
        # A new flow first reveals points, then identity. Existing shows retain their timeline.
        top_index, part = divmod(position - jury_start, 2) if flow_version >= 2 else (position - jury_start, 1)
        reveal_identity = part == 1
        frame["scene"] = "jury_top" if reveal_identity else "jury_points"
        top_queue = list(reversed(jury_order[:top_count]))
        cid = top_queue[top_index]
        r = rows[cid]
        known_jury = set(jury_order[top_count:]) | set(top_queue[:top_index + int(reveal_identity)])
        frame["jury_sequence"] = top_index + 1
        frame["jury_points"] = r["jury_points"]
        if reveal_identity:
            frame["current"] = {"number": r["number"], "name": r["name"], "jury": r["jury_points"],
                "audience": None, "total": r["jury_points"], "sequence": top_index + 1}
        frame["headline"] = "Рішення журі"
    elif position >= results_position(result, flow_version):
        offset = position - results_position(result, flow_version)
        places = podium_places(result)
        frame["scene"] = "final" if offset == 0 else "podium" if offset <= len(places) else "victory"
        frame["award_place"] = places[offset - 1] if frame["scene"] == "podium" else 1 if frame["scene"] == "victory" else None
        shown = set(order)
        frame["notices"] = result["warnings"]
    else:
        index, substep = divmod(position - start, 3)
        frame["scene"] = ["contestant", "audience", "combined"][substep]
        cid = order[index]
        r = rows[cid]
        shown = set(order[:index + (substep == 2)])
        frame["current"] = {"number": r["number"], "name": r["name"], "jury": r["jury_points"],
            "audience": r["audience_points"] if substep >= 1 else None,
            "total": r["total"] if substep == 2 else None, "sequence": index + 1}
    frame["revealed"] = len(shown)
    def score(cid, revealed):
        return Fraction(rows[cid]["jury_exact"]["fraction"]) + (Fraction(rows[cid]["audience_exact"]["fraction"]) if cid in revealed else 0)
    def ranking_key(cid):
        r = rows[cid]
        return (score(cid, shown), Fraction(r["audience_exact"]["fraction"]) if cid in shown else 0,
                r["votes"] if cid in shown else 0, r["fives"], r["threes"], r["ones"])
    ranked = sorted(rows, key=lambda cid: (*(-value for value in ranking_key(cid)), rows[cid]["original"]))
    rank = 0
    for i, cid in enumerate(ranked):
        if i == 0 or ranking_key(cid) != ranking_key(ranked[i - 1]):
            rank = i + 1
        r = rows[cid]
        if cid not in known_jury:
            # No name, number or score is sent for a jury result awaiting announcement.
            frame["board"].append({"number": None, "name": "Ще не оголошено", "rank": None,
                "jury": None, "audience": None, "total": None, "revealed": False, "current": False, "hidden": True})
            continue
        frame["board"].append({"number": r["number"], "name": r["name"], "rank": rank,
            "jury": r["jury_points"], "audience": r["audience_points"] if cid in shown else None,
            "total": r["jury_points"] + (r["audience_points"] if cid in shown else 0),
            "revealed": cid in shown, "current": frame["current"] is not None and frame["current"]["number"] == r["number"], "hidden": False})
    if frame["scene"] == "combined":
        cid = order[frame["current"]["sequence"] - 1]
        previous = shown - {cid}
        previous_best = max(score(other, previous) for other in rows)
        if ranked[0] == cid and score(cid, shown) > previous_best and score(cid, previous) < previous_best:
            frame["headline"] = "Новий лідер!"
        elif next(r["rank"] for r in frame["board"] if r["number"] == frame["current"]["number"]) <= 3:
            frame["headline"] = "У трійці лідерів"
        else:
            frame["headline"] = "Бали додано"
    if frame["scene"] in {"final", "podium", "victory"}:
        frame["winners"] = [r for r in frame["board"] if r["rank"] == 1]
        frame["headline"] = "Переможець конкурсу" if len(frame["winners"]) == 1 else "Перше місце ділять"
        if frame["award_place"] is not None:
            frame["awardees"] = [r for r in frame["board"] if r["rank"] == frame["award_place"]]
            if frame["scene"] == "podium":
                frame["headline"] = {3: "Третє місце", 2: "Друге місце", 1: "Перше місце"}[frame["award_place"]]
                if len(frame["awardees"]) > 1:
                    frame["headline"] += " — ділять учасники"
            else:
                frame["headline"] = "Вітаємо переможця!" if len(frame["winners"]) == 1 else "Вітаємо переможців!"
    frame["stage_label"] = {
        "jury": "ЖУРІ · ПЕРШІ РЕЗУЛЬТАТИ",
        "jury_points": "ЖУРІ · СПОЧАТКУ БАЛИ",
        "jury_top": "ЖУРІ · ОГОЛОШУЄМО УЧАСНИКА",
        "contestant": "ГЛЯДАЧІ · ЧЕКАЄМО НА БАЛИ",
        "audience": "ГЛЯДАЧІ · БАЛИ ОГОЛОШЕНО",
        "combined": "СУМУ ОНОВЛЕНО · ЖУРІ + ГЛЯДАЧІ",
        "final": "ПІДСУМКОВІ РЕЗУЛЬТАТИ",
        "podium": "НАГОРОДЖЕННЯ",
        "victory": "ВІТАЄМО ПЕРЕМОЖЦЯ!",
    }.get(frame["scene"], "ОГОЛОШЕННЯ РЕЗУЛЬТАТІВ")
    return frame
