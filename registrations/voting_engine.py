"""Pure, deterministic competition validation and exact scoring."""
from fractions import Fraction
from uuid import uuid4, UUID
from collections import Counter
from decimal import Decimal, localcontext

STEPS = ["Журі", "Учасники", "Фіналісти", "Голоси глядачів", "Оцінки журі", "Результати", "Сценарій ведучого"]


class VotingError(ValueError):
    pass


def key():
    return str(uuid4())


def initial_state():
    return {"jury": [{"id": key(), "code": code, "name": "", "active": True} for code in "ABC"],
            "contestants": [], "shortlist": {"enabled": False, "target": 0, "confirmed": False},
            "ballots": {"total": 0, "invalid": 0, "votes": {}}, "scores": {}}


def integer(value, label, maximum=1000000000):
    if type(value) is not int or not 0 <= value <= maximum:
        raise VotingError(f"{label}: введіть ціле невід’ємне число (не більше {maximum}).")
    return value


def text(value, label, maximum=200):
    if not isinstance(value, str) or len(value) > maximum:
        raise VotingError(f"{label}: текст має містити не більше {maximum} символів.")
    return value.strip()


def identity(value):
    try:
        return str(UUID(value))
    except (ValueError, TypeError, AttributeError):
        raise VotingError("Не вдалося визначити учасника. Оновіть сторінку.")


def clean_state(data, previous):
    """Validate the shape even for incomplete autosaved drafts. Never trust browser calculations."""
    if not isinstance(data, dict):
        raise VotingError("Не вдалося прочитати дані.")
    jury = data.get("jury", [])
    people = data.get("contestants", [])
    if not isinstance(jury, list) or not isinstance(people, list) or len(jury) > 200 or len(people) > 2000:
        raise VotingError("Забагато рядків: підтримується до 200 членів журі та 2000 учасників.")
    old_codes = {j["id"]: j["code"] for j in previous.get("jury", [])}
    out_jury, out_people = [], []
    for j in jury:
        jid = identity(j.get("id"))
        code = text(j.get("code"), "Позначення журі", 8)
        if not code.isalpha() or not code.isascii() or not code.isupper() or old_codes.get(jid, code) != code:
            raise VotingError("Позначення члена журі змінювати не можна.")
        out_jury.append({"id": jid, "code": code, "name": text(j.get("name", ""), "Ім’я журі"), "active": j.get("active") is True})
    if len({j["id"] for j in out_jury}) != len(out_jury) or len({j["code"] for j in out_jury}) != len(out_jury):
        raise VotingError("Члени журі повинні мати різні позначення.")
    if not set(old_codes).issubset({j["id"] for j in out_jury}):
        raise VotingError("Члена журі не видаляють: зніміть позначку «Бере участь».")
    for c in people:
        out_people.append({"id": identity(c.get("id")), "original": integer(c.get("original"), "Номер учасника", 100000),
            "name": text(c.get("name", ""), "Ім’я учасника"), "phone": text(c.get("phone", ""), "Телефон", 80),
            "instagram": text(c.get("instagram", ""), "Instagram", 240), "finalist": c.get("finalist") is True,
            "final": None, "dq": c.get("dq") is True, "reason": text(c.get("reason", ""), "Причина дискваліфікації", 2000)})
    if len({c["id"] for c in out_people}) != len(out_people):
        raise VotingError("Знайдено повтор учасника. Оновіть сторінку.")
    sl = data.get("shortlist", {})
    shortlist = {"enabled": sl.get("enabled") is True, "target": integer(sl.get("target", 0), "Кількість фіналістів", 2000), "confirmed": sl.get("confirmed") is True}
    active_index = 0
    for c in out_people:
        if c["name"] and (not shortlist["enabled"] or c["finalist"]):
            active_index += 1
            c["final"] = active_index if shortlist["enabled"] else c["original"]
    ids = {c["id"] for c in out_people}
    ballots = data.get("ballots", {})
    votes = ballots.get("votes", {})
    scores = data.get("scores", {})
    if not isinstance(votes, dict) or not isinstance(scores, dict):
        raise VotingError("Не вдалося прочитати голоси.")
    result = {"jury": out_jury, "contestants": out_people, "shortlist": shortlist,
        "ballots": {"total": integer(ballots.get("total", 0), "Усього бюлетенів"), "invalid": integer(ballots.get("invalid", 0), "Недійсні бюлетені"),
                    "votes": {cid: integer(v, "Голоси учасника") for cid, v in votes.items() if cid in ids}}, "scores": {}}
    jury_ids = {j["id"] for j in out_jury}
    for jid, cells in scores.items():
        if jid not in jury_ids:
            continue
        if not isinstance(cells, dict) or any(type(v) is not int or v not in (0, 1, 3, 5) for v in cells.values()):
            raise VotingError("Журі може поставити лише 0, 1, 3 або 5 балів.")
        result["scores"][jid] = {cid: v for cid, v in cells.items() if cid in ids}
    return result


def finalists(state):
    return [c for c in state["contestants"] if c["name"] and (not state["shortlist"]["enabled"] or c["finalist"])]


def validate(state, stage):
    if not any(j["active"] for j in state["jury"]):
        raise VotingError("Залиште хоча б одного члена журі.")
    if any(not j["name"] for j in state["jury"] if j["active"]):
        raise VotingError("Вкажіть ім’я кожного члена журі, який бере участь.")
    if stage < 2:
        return
    people = [c for c in state["contestants"] if c["name"]]
    if len(people) < 3:
        raise VotingError("Для оцінювання 5 / 3 / 1 потрібно щонайменше троє учасників.")
    numbers = [c["original"] for c in people]
    if 0 in numbers or len(set(numbers)) != len(numbers):
        raise VotingError("Вкажіть різні додатні реєстраційні номери учасників.")
    if stage < 3:
        return
    sl = state["shortlist"]
    if sl["enabled"]:
        if not 3 <= sl["target"] < len(people):
            raise VotingError("Оберіть кількість фіналістів від 3 до числа, меншого за кількість учасників.")
        if len(finalists(state)) != sl["target"]:
            raise VotingError(f"Оберіть рівно {sl['target']} фіналістів. Зараз обрано {len(finalists(state))}.")
    if stage < 4:
        return
    b = state["ballots"]
    if b["invalid"] > b["total"]:
        raise VotingError("Недійсних бюлетенів не може бути більше, ніж усіх бюлетенів у скриньці.")
    votes = sum(b["votes"].get(c["id"], 0) for c in finalists(state))
    difference = votes - (b["total"] - b["invalid"])
    if difference > 0:
        raise VotingError(f"Введено на {difference} голосів більше, ніж є дійсних бюлетенів.")
    if difference < 0:
        raise VotingError(f"Потрібно внести ще {-difference} голосів, щоб збіглася кількість дійсних бюлетенів.")
    if stage < 5:
        if len([c for c in finalists(state) if not c["dq"]]) < 3:
            raise VotingError("Перед початком оцінювання журі потрібно щонайменше троє недискваліфікованих фіналістів.")
        return
    for j in state["jury"]:
        if not j["active"]:
            continue
        counts = Counter(state["scores"].get(j["id"], {}).get(c["id"], 0) for c in finalists(state))
        for award in (5, 3, 1):
            if counts[award] != 1:
                raise VotingError(f"Журі {j['code']} ({j['name']}): " + (f"ще не поставлено {award} балів." if not counts[award] else f"оцінку {award} поставлено кільком учасникам. Залиште одну."))


def exact(value):
    with localcontext() as ctx:
        ctx.prec = 40
        return {"fraction": f"{value.numerator}/{value.denominator}", "decimal": str(Decimal(value.numerator) / Decimal(value.denominator))}


def allocate(rows, pool, field, tie):
    denominator = sum(r[field] for r in rows)
    if not denominator:
        raise VotingError("Немає голосів для розподілу балів. Перевірте голоси та дискваліфікації.")
    values = {r["id"]: Fraction(r[field] * pool, denominator) for r in rows}
    points = {cid: v.numerator // v.denominator for cid, v in values.items()}
    remaining = pool - sum(points.values())
    # Registration order is used only after all specified meaningful rounding tie-breaks.
    ordered = sorted(rows, key=lambda r: (-(values[r["id"]] % 1), *(-v for v in tie(r)), r["original"]))
    notices = []
    for r in ordered[:remaining]:
        points[r["id"]] += 1
    if 0 < remaining < len(ordered):
        a, b = ordered[remaining - 1], ordered[remaining]
        if values[a["id"]] % 1 == values[b["id"]] % 1:
            notices.append(f"Розподіл {pool} балів: однакові дробові залишки біля останнього додаткового бала; застосовано правила пріоритету, а за повної рівності — реєстраційний порядок.")
    return values, points, notices


def calculate(state):
    validate(state, 5)
    b = state["ballots"]
    rows = []
    for c in state["contestants"]:
        if not c["name"]:
            continue
        awards = Counter(state["scores"].get(j["id"], {}).get(c["id"], 0) for j in state["jury"] if j["active"])
        active = c in finalists(state)
        rows.append({"id": c["id"], "original": c["original"], "number": c["final"], "name": c["name"],
            "status": "Дискваліфіковано" if c["dq"] and active else "Фіналіст" if active else "Не у фіналі",
            "reason": c["reason"] if c["dq"] else "", "eligible": active and not c["dq"],
            "votes": b["votes"].get(c["id"], 0), "fives": awards[5], "threes": awards[3], "ones": awards[1],
            "jury_raw": awards[5] * 5 + awards[3] * 3 + awards[1], "rank": None,
            "audience_points": 0, "jury_points": 0, "total": 0,
            "audience_exact": exact(Fraction(0)), "jury_exact": exact(Fraction(0)), "combined_exact": exact(Fraction(0)),
            "audience_percent": "0", "jury_percent": "0"})
    eligible = [r for r in rows if r["eligible"]]
    av, ap, an = allocate(eligible, 750, "votes", lambda r: (r["votes"],))
    jv, jp, jn = allocate(eligible, 250, "jury_raw", lambda r: (r["fives"], r["threes"], r["ones"]))
    for r in eligible:
        cid = r["id"]
        r.update(audience_points=ap[cid], jury_points=jp[cid], total=ap[cid] + jp[cid], audience_exact=exact(av[cid]), jury_exact=exact(jv[cid]), combined_exact=exact(av[cid] + jv[cid]), audience_percent=exact(av[cid] * 100 / 750)["decimal"], jury_percent=exact(jv[cid] * 100 / 250)["decimal"])
    rank_key = lambda r: (av[r["id"]] + jv[r["id"]], av[r["id"]], r["votes"], r["fives"], r["threes"], r["ones"])
    ranked = sorted(eligible, key=lambda r: (*(-v for v in rank_key(r)), r["original"]))
    warnings = []
    for i, r in enumerate(ranked):
        r["rank"] = ranked[i - 1]["rank"] if i and rank_key(ranked[i - 1]) == rank_key(r) else i + 1
        if i and av[r["id"]] + jv[r["id"]] == av[ranked[i - 1]["id"]] + jv[ranked[i - 1]["id"]]:
            previous = ranked[i - 1]
            if rank_key(r) == rank_key(previous):
                warnings.append(f"Учасники №{previous['number']} і №{r['number']} ділять {r['rank']}-те місце: усі критерії рівні.")
            else:
                warnings.append(f"Увага: застосовано правило тай-брейку. Учасники №{previous['number']} і №{r['number']} мали однаковий точний результат. Вище місце визначено послідовністю: результат глядачів, кількість голосів, оцінки журі 5 / 3 / 1.")
    original_jury_order = sorted([r for r in rows if r["number"]], key=lambda r: (-r["jury_raw"], -r["fives"], -r["threes"], -r["ones"], r["original"]))
    result = {"rows": ranked + [r for r in rows if not r["eligible"]], "warnings": warnings, "rounding_notices": an + jn,
        "total_ballots": b["total"], "invalid_ballots": b["invalid"], "valid_ballots": b["total"] - b["invalid"],
        "excluded_votes": sum(r["votes"] for r in rows if r["status"] == "Дискваліфіковано"),
        "eligible_votes": sum(r["votes"] for r in eligible), "eligible_jury": sum(r["jury_raw"] for r in eligible),
        "jury": [j for j in state["jury"] if j["active"]],
        "jury_table": [{"number": r["number"], "name": r["name"], "scores": [state["scores"].get(j["id"], {}).get(r["id"], 0) for j in state["jury"] if j["active"]]} for r in original_jury_order],
        "reveal_order": [r["id"] for r in reversed(original_jury_order) if r["eligible"]]}
    assert sum(r["audience_points"] for r in rows) == 750
    assert sum(r["jury_points"] for r in rows) == 250
    return result
