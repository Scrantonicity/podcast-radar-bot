"""stats.py — everything the observatory counts.

Pure: `compute(episodes, transcripts, show, obs)` takes already-loaded data and
returns one JSON-ready dict. No file I/O, no network, no globals — so the tests
hand it fixtures and the entry point hands it the real archive, and neither knows
the difference.

Two rules shape this module:

1. **Numbers live here, words don't.** Nothing returned by this file is a sentence.
   Facts and records emit `{"value": ..., "data": {...}}`; the show's Copy supplies
   the template that renders them. That's what stops a caption saying "88.9 hours"
   forever after the archive grows (see OBSERVATORY.md).

2. **Everything is keyed by the show's own entity_types.** No literal "person" or
   "stock" gates a feature. A show that redefines its taxonomy gets a page that
   follows, and one that drops a type just loses that card.

Ported from the original single-show build's stats module, which computed the same
numbers for one Hebrew show with the taxonomy, hosts, and captions inlined.
"""

import re
from collections import defaultdict

from . import place_coords

# Reading types get a shelf of their own; sentiment types get a ticker. Both are
# already declared per-show on ShowConfig, so read them there rather than guessing.
_TICKER_RE = re.compile(r"^[A-Z0-9.\-]{1,6}$")
_SPEAKER_TAG_RE = re.compile(r"\[S\d+\]")
_LATIN_RE = re.compile(r"[A-Za-z][A-Za-z']+")


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------
def dur_sec(s):
    """'1:02:03' or '58:10' -> seconds. Junk -> 0 (the episode is left untimed)."""
    try:
        p = [int(x) for x in str(s).split(":")]
    except (ValueError, AttributeError):
        return 0
    if len(p) == 3:
        return p[0] * 3600 + p[1] * 60 + p[2]
    if len(p) == 2:
        return p[0] * 60 + p[1]
    return 0


def fmt_hm(sec):
    return f"{sec // 3600}:{(sec % 3600) // 60:02d}"


def _ep_meta(ep):
    e = ep.get("episode") or {}
    return {
        "number": e.get("number"),
        "title": e.get("title") or "",
        "headline": ep.get("headline") or e.get("headline") or "",
        "date": e.get("date") or "",
        "duration": e.get("duration") or "",
        "guid": e.get("guid") or "",
    }


def _labeler(copy):
    """Episodes are named in ~10 places; build the namer once."""
    def label(meta):
        n = meta["number"]
        if n is not None:
            return copy.episode_label_tpl.format(n=n)
        return meta["headline"] or copy.episode_unnumbered
    return label


def _sort_eps(rows):
    """Unnumbered episodes (specials) sort last, not as number 0."""
    return sorted(rows, key=lambda x: (x["number"] is None, x["number"] or 0))


# ---------------------------------------------------------------------------
# aggregation
# ---------------------------------------------------------------------------
def _aggregate(episodes, show, label):
    """Fold every episode's entities into one record per canonical_key.

    `mentions` counts EPISODES the entity appeared in, not utterances — the
    extraction contract already merges repeats within an episode, so this is the
    only number the data can honestly support.
    """
    ents, ep_entity_keys = {}, []
    native_re = re.compile(show.native_script_re) if show.native_script_re else None

    for ep in episodes:
        meta = _ep_meta(ep)
        keys_here = set()
        for ent in ep.get("entities") or []:
            name = (ent.get("name") or "").strip()
            ek = (ent.get("canonical_key") or name or "").strip().lower()
            if not name or not ek:
                continue
            rec = ents.get(ek)
            if rec is None:
                rec = {
                    "key": ek, "name": name, "type": ent.get("type") or "other",
                    "notability": ent.get("notability") or 0,
                    "one_liner": ent.get("one_liner") or "",
                    "ticker": ent.get("ticker"), "link": ent.get("link"),
                    "hosts": set(), "episodes": {},
                }
                ents[ek] = rec
            # Merge: keep the richest value seen for each field.
            rec["notability"] = max(rec["notability"], ent.get("notability") or 0)
            if not rec["one_liner"] and ent.get("one_liner"):
                rec["one_liner"] = ent["one_liner"]
            if not rec["ticker"] and ent.get("ticker"):
                rec["ticker"] = ent["ticker"]
            if not rec["link"] and ent.get("link"):
                rec["link"] = ent["link"]
            # A name in the show's own script beats a Latin transliteration of it.
            if native_re and native_re.search(name) and not native_re.search(rec["name"]):
                rec["name"] = name
            # mentioned_by is enum-constrained at extraction, so no alias map needed.
            for h in ent.get("mentioned_by") or []:
                rec["hosts"].add(h)
            rec["episodes"][meta["guid"] or label(meta)] = {
                "number": meta["number"], "title": meta["title"],
                "headline": meta["headline"], "date": meta["date"],
                "timestamp": ent.get("timestamp"), "label": label(meta),
            }
            keys_here.add(ek)
        ep_entity_keys.append((meta, keys_here))

    for rec in ents.values():
        rec["hosts"] = sorted(rec["hosts"])
        rec["mentions"] = len(rec["episodes"])
        rec["episode_list"] = _sort_eps(list(rec["episodes"].values()))
    return ents, ep_entity_keys


def _trim(s, n=200):
    """One-liners land in the page's payload; a runaway one is pure page weight."""
    s = s or ""
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


# ---------------------------------------------------------------------------
# fun facts — each builder returns {"icon", "value", "data"} or None
#
# `data` is what the show's caption template interpolates. Add a field here and it
# becomes available to every show's copy; the ids are the contract with
# defaults.DEFAULT_FUNFACT_COPY and OBSERVATORY.md.
# ---------------------------------------------------------------------------
def _fact_regular_star(c):
    people = [e for e in c["all_ents"] if e["type"] == "person"]
    top = max(people, key=lambda e: e["mentions"], default=None)
    if not top or top["mentions"] < 2:
        return None
    pct = round(100 * top["mentions"] / max(1, c["n_eps"]))
    return {"icon": "👑", "value": f"{top['mentions']}/{c['n_eps']}",
            "data": {"name": top["name"], "n": top["mentions"],
                     "eps": c["n_eps"], "pct": pct}}


def _fact_social_butterfly(c):
    if not c["all_ents"]:
        return None
    top = max(c["all_ents"], key=lambda e: len(c["neigh"].get(e["key"], ())))
    deg = len(c["neigh"].get(top["key"], ()))
    if deg < 2:
        return None
    return {"icon": "🦋", "value": str(deg), "data": {"name": top["name"], "n": deg}}


def _fact_inseparable_pair(c):
    if not c["arcs"]:
        return None
    a = c["arcs"][0]
    if a["w"] < 2:
        return None
    return {"icon": "💞", "value": f"×{a['w']}",
            "data": {"a": c["pname"](a["a"]), "b": c["pname"](a["b"]), "n": a["w"]}}


def _fact_one_hit_wonders(c):
    n = len([e for e in c["all_ents"] if e["mentions"] == 1])
    if not n:
        return None
    pct = round(100 * n / max(1, len(c["all_ents"])))
    return {"icon": "🎯", "value": f"{pct}%", "data": {"n": n, "pct": pct}}


def _fact_globetrotter_host(c):
    if not c["host_places"]:
        return None
    host, places = max(c["host_places"].items(), key=lambda x: len(x[1]))
    if not places:
        return None
    return {"icon": "🧭", "value": str(len(places)),
            "data": {"host": host, "n": len(places)}}


def _fact_lightest_episode(c):
    if not c["dur_rows"]:
        return None
    r = min(c["dur_rows"], key=lambda r: r["sec"])
    return {"icon": "🪶", "value": r["dur"],
            "data": {"label": r["label"], "dur": r["dur"], "number": r["number"]}}


def _fact_marathon(c):
    if not c["dur_rows"]:
        return None
    r = max(c["dur_rows"], key=lambda r: r["sec"])
    return {"icon": "⏳", "value": fmt_hm(r["sec"]),
            "data": {"label": r["label"], "dur": r["dur"], "number": r["number"]}}


def _fact_average_episode(c):
    if not c["timeline"]:
        return None
    avg = round(sum(t["total"] for t in c["timeline"]) / len(c["timeline"]), 1)
    mins = c["content"]["avg_min"]
    return {"icon": "🏛️", "value": str(avg), "data": {"n": avg, "mins": mins}}


def _fact_hours_in_ears(c):
    h = c["content"]["total_hours"]
    if not h:
        return None
    return {"icon": "🎙️", "value": str(h),
            "data": {"hours": h, "days": round(h / 24, 1)}}


def _fact_returning_faces(c):
    n = len([e for e in c["all_ents"] if e["mentions"] >= 2])
    if not n:
        return None
    pct = round(100 * n / max(1, len(c["all_ents"])))
    return {"icon": "🔁", "value": str(n), "data": {"n": n, "pct": pct}}


def _fact_rarest_gem(c):
    top_notability = max((e["notability"] for e in c["all_ents"]), default=0)
    if top_notability < 5:
        return None
    n = len([e for e in c["all_ents"] if e["notability"] >= 5])
    return {"icon": "💎", "value": str(n), "data": {"n": n}}


def _fact_reading_shelf(c):
    n = len([e for e in c["all_ents"] if e["type"] in c["show"].reading_types])
    if not n:
        return None
    books = len([e for e in c["all_ents"] if e["type"] == "book"])
    return {"icon": "📚", "value": str(n),
            "data": {"n": n, "books": books, "articles": n - books,
                     "per_ep": round(n / max(1, c["n_eps"]), 1)}}


def _fact_world_vs_market(c):
    """Off by default: only means something for a show whose editorial line is
    world-affairs vs markets. Opt in via funfact_order."""
    geo = sum(e["mentions"] for e in c["all_ents"] if e["type"] in ("place", "person"))
    mkt = sum(e["mentions"] for e in c["all_ents"] if e["type"] in ("stock", "company"))
    if not geo or not mkt:
        return None
    ratio = round(geo / mkt, 1)
    return {"icon": "⚖️", "value": f"{ratio}:1", "data": {"ratio": ratio}}


def _fact_longest_name(c):
    named = [e for e in c["all_ents"] if e["name"]]
    if not named:
        return None
    e = max(named, key=lambda e: len(e["name"]))
    return {"icon": "📏", "value": str(len(e["name"])),
            "data": {"name": e["name"], "len": len(e["name"]),
                     "type": c["type_labels"].get(e["type"], e["type"])}}


def _fact_all_the_types(c):
    n = len(c["type_totals"])
    if n < 2:
        return None
    return {"icon": "🧠", "value": str(n),
            "data": {"n": n, "kinds": ", ".join(
                c["type_labels"].get(t, t) for t in sorted(c["type_totals"]))}}


def _fact_word_avalanche(c):
    w = c["words"]
    if not w or not w.get("total"):
        return None
    total = w["total"]
    # Only abbreviate when there's something to abbreviate: 483 // 1000 is "0K".
    value = f"{total // 1000}K" if total >= 10000 else f"{total:,}"
    return {"icon": "🗯️", "value": value,
            "data": {"n": f"{total:,}", "per_ep": f"{w['per_ep']:,}"}}


def _fact_busiest_episode(c):
    if not c["timeline"]:
        return None
    t = max(c["timeline"], key=lambda x: x["total"])
    if not t["total"]:
        return None
    return {"icon": "🎬", "value": str(t["total"]),
            "data": {"label": t["label"], "n": t["total"],
                     "headline": t["headline"], "number": t["number"]}}


FACT_BUILDERS = {
    "regular_star": _fact_regular_star,
    "social_butterfly": _fact_social_butterfly,
    "inseparable_pair": _fact_inseparable_pair,
    "one_hit_wonders": _fact_one_hit_wonders,
    "globetrotter_host": _fact_globetrotter_host,
    "lightest_episode": _fact_lightest_episode,
    "marathon": _fact_marathon,
    "average_episode": _fact_average_episode,
    "hours_in_ears": _fact_hours_in_ears,
    "returning_faces": _fact_returning_faces,
    "rarest_gem": _fact_rarest_gem,
    "reading_shelf": _fact_reading_shelf,
    "world_vs_market": _fact_world_vs_market,
    "longest_name": _fact_longest_name,
    "all_the_types": _fact_all_the_types,
    "word_avalanche": _fact_word_avalanche,
    "busiest_episode": _fact_busiest_episode,
}


class _SafeDict(dict):
    """A caption naming a field the fact doesn't emit renders the marker literally
    instead of raising — a typo in one show's copy must not fail the build. The
    dry-run report names it so it still gets fixed."""

    def __missing__(self, key):
        return "{" + key + "}"


def _render_facts(ctx, copy):
    """A fact renders only if: its builder found data, its id is in funfact_order,
    and the show wrote copy for it. Anything else is skipped and reported."""
    out, skipped = [], []
    for fid in copy.funfact_order:
        builder = FACT_BUILDERS.get(fid)
        if not builder:
            skipped.append((fid, "no such fact"))
            continue
        try:
            got = builder(ctx)
        except (ValueError, TypeError, KeyError, ZeroDivisionError) as e:
            skipped.append((fid, f"builder error: {e}"))
            continue
        if not got:
            skipped.append((fid, "not enough data"))
            continue
        text = copy.funfact_copy.get(fid)
        if not text:
            skipped.append((fid, "no copy"))
            continue
        out.append({
            "id": fid, "icon": got["icon"], "value": got["value"],
            "title": text.get("title", ""),
            "cap": str(text.get("cap", "")).format_map(_SafeDict(got["data"])),
        })
    return out, skipped


# ---------------------------------------------------------------------------
# the main pass
# ---------------------------------------------------------------------------
def compute(episodes, transcripts, show, obs):
    """episodes: list of extraction contracts. transcripts: {guid: text} (may be
    empty). show: ShowConfig. obs: a RESOLVED Observatory (see defaults.resolve).

    Returns (stats, report) — report carries what the build wants to tell a human
    (ungeocoded places, skipped facts, gate decisions).
    """
    if not episodes:
        raise ValueError(
            "no episodes to build from — the extractions directory is empty. "
            "Run the pipeline first, or pass --extractions at a directory that has "
            "episode json in it."
        )

    copy = obs.copy
    label = _labeler(copy)
    types = tuple(show.entity_types)
    ents, ep_entity_keys = _aggregate(episodes, show, label)
    all_ents = list(ents.values())
    n_eps = len(episodes)

    def by_type(t):
        return [e for e in all_ents if e["type"] == t]

    type_totals = defaultdict(int)
    for e in all_ents:
        type_totals[e["type"]] += 1
    type_totals = dict(type_totals)

    # --- places + coords ----------------------------------------------------
    ungeocoded = defaultdict(int)
    places, place_key_by_ekey = [], {}
    for e in by_type("place"):
        coord = place_coords.lookup(e["key"], e["name"],
                                    obs.extra_place_coords, obs.place_key_aliases)
        if coord is None:
            ungeocoded[e["key"] or e["name"]] += e["mentions"]
            continue
        ck = obs.place_key_aliases.get(e["key"], e["key"])
        place_key_by_ekey[e["key"]] = ck
        places.append({
            "name": e["name"], "key": ck, "lat": coord[0], "lon": coord[1],
            "mentions": e["mentions"], "notability": e["notability"],
            "one_liner": _trim(e["one_liner"]), "hosts": e["hosts"],
            "episodes": [{"number": x["number"], "label": x["label"],
                          "title": x["title"], "timestamp": x["timestamp"]}
                         for x in e["episode_list"]],
        })
    places.sort(key=lambda p: -p["mentions"])

    # --- arcs: places named in the same episode -----------------------------
    pair_w = defaultdict(int)
    for _meta, keys in ep_entity_keys:
        pk = sorted({place_key_by_ekey[k] for k in keys if k in place_key_by_ekey})
        for i in range(len(pk)):
            for j in range(i + 1, len(pk)):
                pair_w[(pk[i], pk[j])] += 1
    arcs = sorted(({"a": a, "b": b, "w": w} for (a, b), w in pair_w.items()),
                  key=lambda x: -x["w"])[:130]

    # --- the shelf ----------------------------------------------------------
    reading = [t for t in show.reading_types if t in types]
    books = []
    for t in reading:
        for e in by_type(t):
            first = e["episode_list"][0] if e["episode_list"] else {}
            books.append({
                "name": e["name"], "type": e["type"], "one_liner": _trim(e["one_liner"]),
                "notability": e["notability"], "mentions": e["mentions"],
                "hosts": e["hosts"], "link": e["link"],
                "ep": first.get("number"), "ep_label": first.get("label", ""),
                "episodes": [{"number": x["number"], "label": x["label"]}
                             for x in e["episode_list"]],
            })
    books.sort(key=lambda b: (-b["notability"], -b["mentions"]))

    concepts = sorted(
        ({"name": e["name"], "mentions": e["mentions"], "notability": e["notability"],
          "one_liner": _trim(e["one_liner"]), "hosts": e["hosts"]}
         for e in by_type("concept")),
        key=lambda c: -c["mentions"])

    # --- timeline: counts per type; the template groups them into streams ----
    timeline = []
    for meta, keys in ep_entity_keys:
        by = defaultdict(int)
        for k in keys:
            by[ents[k]["type"]] += 1
        timeline.append({
            "number": meta["number"], "date": meta["date"], "label": label(meta),
            "headline": meta["headline"], "total": len(keys), "by": dict(by),
        })
    timeline = _sort_eps(timeline)

    # --- duration -----------------------------------------------------------
    dur_rows = []
    for ep in episodes:
        m = _ep_meta(ep)
        s = dur_sec(m["duration"])
        if s > 0:
            dur_rows.append({"label": label(m), "number": m["number"], "sec": s,
                             "dur": m["duration"], "headline": m["headline"]})
    tot_sec = sum(r["sec"] for r in dur_rows)
    content = {
        "total_sec": tot_sec,
        "total_hours": round(tot_sec / 3600, 1),
        "avg_min": round(tot_sec / len(dur_rows) / 60) if dur_rows else 0,
        "episodes_timed": len(dur_rows),
        "longest": max(dur_rows, key=lambda r: r["sec"]) if dur_rows else None,
        "shortest": min(dur_rows, key=lambda r: r["sec"]) if dur_rows else None,
    }

    # --- words: only if transcripts were kept -------------------------------
    words = _words(transcripts, show, copy, n_eps)

    # --- host attribution ---------------------------------------------------
    # Guests are excluded: the face-off compares the show's regulars, and a guest
    # appears in one episode so their totals aren't comparable anyway.
    host_type_counts = defaultdict(lambda: defaultdict(int))
    host_counts = defaultdict(int)
    host_places = defaultdict(set)
    regulars = set(show.hosts)
    for e in all_ents:
        for h in e["hosts"]:
            if h not in regulars:
                continue
            host_counts[h] += e["mentions"]
            host_type_counts[h][e["type"]] += e["mentions"]
            if e["type"] == "place":
                host_places[h].add(e["key"])

    host_face = _host_face(host_type_counts, copy, obs, show)

    # --- superlatives -------------------------------------------------------
    def slim(e):
        if not e:
            return None
        return {"name": e["name"], "mentions": e["mentions"],
                "one_liner": _trim(e["one_liner"]), "notability": e["notability"],
                "ticker": e.get("ticker")}

    top_by_type = {}
    for t in types:
        lst = sorted(by_type(t), key=lambda e: -e["mentions"])
        if lst:
            top_by_type[t] = slim(lst[0])

    ep_place_counts = [
        (label(meta), meta["number"], meta["headline"],
         len({place_key_by_ekey[k] for k in keys if k in place_key_by_ekey}))
        for meta, keys in ep_entity_keys
    ]
    most_places = max(ep_place_counts, key=lambda x: x[3], default=None)
    named = [e for e in all_ents if e["name"]]
    longest = max(named, key=lambda e: len(e["name"]), default=None)
    gems = sorted((e for e in all_ents if e["notability"] >= 5),
                  key=lambda e: (e["mentions"], -len(e["name"])))

    superlatives = {
        "top": top_by_type,
        "gems": [slim(g) for g in gems[:6]],
        "busiest": max(timeline, key=lambda x: x["total"]) if timeline else None,
        "most_places": ({"label": most_places[0], "number": most_places[1],
                         "headline": most_places[2], "count": most_places[3]}
                        if most_places and most_places[3] else None),
        "host_counts": dict(host_counts),
        "host_type_counts": {h: dict(v) for h, v in host_type_counts.items()},
        "longest_name": ({"name": longest["name"], "len": len(longest["name"]),
                          "type": longest["type"]} if longest else None),
        "type_totals": type_totals,
    }

    # --- co-mention neighbourhoods (facts + graph both need this) -----------
    neigh = defaultdict(set)
    for _meta, keys in ep_entity_keys:
        kl = sorted(keys)
        for i in range(len(kl)):
            for j in range(i + 1, len(kl)):
                neigh[kl[i]].add(kl[j])
                neigh[kl[j]].add(kl[i])

    def pname(k):
        for p in places:
            if p["key"] == k:
                return p["name"]
        return k

    ctx = {
        "all_ents": all_ents, "ents": ents, "n_eps": n_eps, "timeline": timeline,
        "places": places, "arcs": arcs, "content": content, "words": words,
        "neigh": neigh, "dur_rows": dur_rows, "type_totals": type_totals,
        "host_places": host_places, "show": show, "pname": pname,
        "type_labels": copy.type_labels,
    }
    funfacts, skipped_facts = _render_facts(ctx, copy)

    # --- leaderboards + tickers --------------------------------------------
    leaderboard = {}
    for t in types:
        rows = sorted(by_type(t), key=lambda e: -e["mentions"])[:15]
        if rows:
            leaderboard[t] = [{"name": e["name"], "mentions": e["mentions"],
                               "ticker": e.get("ticker")} for e in rows]

    tickers, seen_tick = [], set()
    for t in show.sentiment_types:
        for e in sorted(by_type(t), key=lambda e: -e["mentions"]):
            tk = (e.get("ticker") or "").strip().upper()
            if tk and tk not in seen_tick and _TICKER_RE.match(tk):
                seen_tick.add(tk)
                tickers.append({"t": tk, "name": e["name"], "m": e["mentions"]})
    tickers.sort(key=lambda x: -x["m"])

    notab_hist = [0, 0, 0, 0, 0]
    for e in all_ents:
        nb = int(e["notability"])
        if 1 <= nb <= 5:
            notab_hist[nb - 1] += 1

    # --- sparklines ---------------------------------------------------------
    spark_nums = [t["number"] for t in timeline if t["number"] is not None]
    spark = []
    for e in sorted(all_ents, key=lambda e: -e["mentions"])[:8]:
        seen = {x["number"] for x in e["episode_list"] if x["number"] is not None}
        spark.append({"name": e["name"], "type": e["type"], "mentions": e["mentions"],
                      "series": [1 if n in seen else 0 for n in spark_nums]})

    graph = _graph(all_ents, ents, ep_entity_keys, obs)

    numbered = [t for t in timeline if t["number"] is not None]
    totals = {
        "episodes": n_eps,
        "entities": len(all_ents),
        "places_geo": len(places),
        "places_total": len(by_type("place")),
        "by_type": type_totals,
        "books": sum(type_totals.get(t, 0) for t in reading),
        "date_from": min((t["date"] for t in numbered if t["date"]), default=""),
        "date_to": max((t["date"] for t in numbered if t["date"]), default=""),
    }

    stats = {
        "totals": totals, "places": places, "arcs": arcs, "books": books,
        "concepts": concepts, "timeline": timeline, "superlatives": superlatives,
        "funfacts": funfacts, "content": content, "words": words,
        "host_face": host_face, "leaderboard": leaderboard, "tickers": tickers,
        "notab_hist": notab_hist, "spark": spark, "spark_nums": spark_nums,
        "shoutouts": [dict(s) for s in copy.shoutout_entries],
        "graph": graph,
    }
    stats["sections"] = gates(stats, obs)

    report = {
        "ungeocoded": sorted(ungeocoded.items(), key=lambda x: -x[1]),
        "skipped_facts": skipped_facts,
        "transcripts_found": len(transcripts or {}),
        "episodes": n_eps,
    }
    return stats, report


def _words(transcripts, show, copy, n_eps):
    """Transcripts are a local cache and may be absent, partial, or turned off. No
    transcripts -> None, and the language section drops the blocks that need it
    rather than showing zeros."""
    if not transcripts:
        return None
    blob = "\n".join(_SPEAKER_TAG_RE.sub(" ", t or "") for t in transcripts.values())
    if not blob.strip():
        return None

    words = {
        "total": len(blob.split()),
        "episodes_covered": len(transcripts),
        "signature": [],
        "laughs": None,
        "latin_words": None,
    }
    # "Words in Latin script" is a real signal for a show in another script and a
    # tautology for an English one, so only count it when the show declares a script.
    if show.native_script_re:
        words["latin_words"] = len(_LATIN_RE.findall(blob))
    for entry in copy.signature_words:
        needle, lbl = (entry if isinstance(entry, (tuple, list)) else (entry, entry))
        c = len(re.findall(re.escape(needle), blob))
        if c:
            words["signature"].append({"w": needle, "count": c, "label": lbl})
    words["signature"].sort(key=lambda x: -x["count"])
    if copy.laugh_pattern:
        try:
            words["laughs"] = len(re.findall(copy.laugh_pattern, blob))
        except re.error:
            words["laughs"] = None   # a bad pattern in copy drops the stat, not the build
    words["per_ep"] = round(words["total"] / max(1, n_eps))
    return words


def _host_face(host_type_counts, copy, obs, show):
    """The face-off is a two-sided chart, so it names exactly two hosts. Default to
    the two with the most attributed mentions; a show with 3+ hosts should say so in
    its section copy."""
    groups = copy.hostface_groups
    rows = []
    for h in show.hosts:
        counts = host_type_counts.get(h)
        if not counts:
            continue
        vals = [sum(counts.get(t, 0) for t in g["types"]) for g in groups]
        rows.append({"host": h, "vals": vals, "total": sum(vals)})
    rows = [r for r in rows if r["total"] > 0]
    rows.sort(key=lambda r: -r["total"])

    if obs.hostface_hosts:
        picked = [r for r in rows if r["host"] in obs.hostface_hosts]
    else:
        picked = rows[:2]
    return {
        "cats": [g["label"] for g in groups],
        "hosts": picked[:2],
        "hosts_available": len(rows),
    }


def _graph(all_ents, ents, ep_entity_keys, obs):
    """Entities linked when they share an episode.

    The thresholds matter more than they look: at a 65-episode archive a weight-3
    floor is a good filter, and at 8 episodes it deletes every edge. defaults.py
    scales them to the archive; this only enforces them.
    """
    ranked = sorted(all_ents, key=lambda e: -e["mentions"])
    keys = {e["key"] for e in ranked if e["mentions"] >= obs.graph_min_mentions}
    if len(keys) > obs.graph_max_nodes:
        keys = {e["key"] for e in ranked[: obs.graph_max_nodes]}
    if len(keys) < 12:   # sparse archive: take the top entities regardless
        keys = {e["key"] for e in ranked[: min(len(ranked), obs.graph_max_nodes)]}

    edge_w = defaultdict(int)
    for _meta, ekeys in ep_entity_keys:
        gk = sorted(k for k in ekeys if k in keys)
        for i in range(len(gk)):
            for j in range(i + 1, len(gk)):
                edge_w[(gk[i], gk[j])] += 1

    strong = sorted(((a, b, w) for (a, b), w in edge_w.items()
                     if w >= obs.graph_min_edge_weight), key=lambda x: -x[2])
    deg, edges = defaultdict(int), []
    for a, b, w in strong:
        if deg[a] >= obs.graph_max_degree or deg[b] >= obs.graph_max_degree:
            continue   # cap degree or the whole thing renders as a hairball
        edges.append((a, b, w))
        deg[a] += 1
        deg[b] += 1
    edges = edges[:280]

    used = {k for a, b, _ in edges for k in (a, b)}
    return {
        "nodes": [{"id": ents[k]["key"], "name": ents[k]["name"],
                   "type": ents[k]["type"], "mentions": ents[k]["mentions"],
                   "one_liner": _trim(ents[k]["one_liner"])} for k in sorted(used)],
        "edges": [{"source": a, "target": b, "w": w} for a, b, w in edges],
    }


# ---------------------------------------------------------------------------
# section gating
# ---------------------------------------------------------------------------
def gates(stats, obs):
    """Decide which sections actually render.

    Gate on the RENDERED OUTPUT, not the ingredients: "there are places" doesn't
    mean the globe has anything to draw, and a section that renders empty looks more
    broken than one that isn't there. A show can also switch any section off
    outright via SectionCopy.enabled.
    """
    c = obs.copy
    w = stats["words"]
    has_words = bool(w and w.get("total"))

    data = {
        # >=3 dots is the least that reads as a map rather than an accident
        "globe": len(stats["places"]) >= 3,
        "library": len(stats["books"]) >= 6,
        "records": bool(stats["superlatives"]["top"]),
        "funfacts": len(stats["funfacts"]) >= 4,
        # two hosts with attribution; blanked diarization lands here as 0
        "hostface": len(stats["host_face"]["hosts"]) >= 2,
        "leaders": bool(stats["leaderboard"]),
        # force-packed bubbles need a crowd to look like anything
        "cloud": len(stats["concepts"]) >= 12,
        "pulse": len(stats["timeline"]) >= 4,
        "wordlab": has_words or len(stats["tickers"]) >= 8,
        "graph": len(stats["graph"]["edges"]) >= 12,
        "shoutouts": bool(stats["shoutouts"]),
    }
    enabled = {
        "globe": c.globe.enabled, "library": c.library.enabled,
        "records": c.records.enabled, "funfacts": c.funfacts.enabled,
        "hostface": c.hostface.enabled, "leaders": c.leaders.enabled,
        "cloud": c.cloud.enabled, "pulse": c.pulse.enabled,
        "wordlab": c.wordlab.enabled, "graph": c.graph.enabled,
        "shoutouts": c.shoutouts.enabled,
    }
    out = {k: bool(data[k] and enabled[k]) for k in data}
    # The language section owns two independent blocks; either can carry it alone.
    out["wordlab_words"] = out["wordlab"] and has_words
    out["wordlab_tickers"] = out["wordlab"] and len(stats["tickers"]) >= 8
    return out
