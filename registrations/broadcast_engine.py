"""Reveal only information that has reached the persisted show position."""
from fractions import Fraction


def jury_top_count(result):
    return min(5, len(result["reveal_order"]))


def audience_start(result):
    return 2 + jury_top_count(result)


def last_position(result):
    return audience_start(result) + 3 * len(result["reveal_order"])


def public_frame(broadcast):
    result = broadcast.snapshot
    rows = {r["id"]: r for r in result["rows"] if r["eligible"]}
    order = result["reveal_order"]
    jury_order = list(reversed(order))
    top_count = jury_top_count(result)
    start = audience_start(result)
    position = min(broadcast.position, last_position(result))
    frame = {"title": broadcast.title, "theme": broadcast.theme, "revision": broadcast.revision,
        "position": position, "last": last_position(result), "count": len(order), "revealed": 0,
        "scene": "welcome", "board": [], "current": None, "winners": [], "notices": [], "headline": "", "top_count": top_count}
    if position == 0:
        return frame
    shown = set()
    known_jury = set(rows)
    if position == 1:
        frame["scene"] = "jury"
        known_jury = set(jury_order[top_count:])
    elif position < start:
        frame["scene"] = "jury_top"
        # The last K contestants of the reverse-jury queue are revealed from Kth to first.
        top_index = position - 2
        top_queue = list(reversed(jury_order[:top_count]))
        cid = top_queue[top_index]
        r = rows[cid]
        known_jury = set(jury_order[top_count:]) | set(top_queue[:top_index + 1])
        frame["current"] = {"number": r["number"], "name": r["name"], "jury": r["jury_points"],
            "audience": None, "total": r["jury_points"], "sequence": top_index + 1}
        frame["headline"] = "Рішення журі"
    elif position == last_position(result):
        frame["scene"] = "final"
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
    if frame["scene"] == "final":
        frame["winners"] = [r for r in frame["board"] if r["rank"] == 1]
        frame["headline"] = "Переможець конкурсу" if len(frame["winners"]) == 1 else "Перше місце ділять"
    return frame
