"""Execution study: when to place, what price, when to cancel, how realistic fills are.
Datasets (full trade tapes with taker side):
  main  = 7 core cities, 2026-09-22..11-19  (used to FIND the rules)
  year  = 7 core cities, before 2026-09-22  (held out: CHECKS the rules)
  extra = 11 extra cities, ~Aug..Nov         (held out: CHECKS the rules)
Two universes per dataset:
  fav     = our strategy: YES on the event's top bucket when its mid is 50-65c
  generic = every bucket priced 20-85c, bought YES and bought NO (strategy-free; much bigger n)
Default fill rule = 'through' (a trade printed below our price), which matched a queue of
100-500 contracts almost exactly on the main data. Returns per $ spent; [..] = 95% luck range
(bootstrap over whole days). 'profit/100 chances' counts unfilled chances as $0.
Usage: python3 exec/execution_study.py main year extra > exec/results.txt
Research only: does not touch the live pick scripts.
"""
import sys
import tape, exp

PLACES = {"6 PM day before": (-1, 18), "7 AM": (0, 7)}


def fill_window(h):
    return ("a) evening before" if h < 0 else "b) 00-09" if h < 9 else "c) 09-12" if h < 12
            else "d) 12-15" if h < 15 else "e) 15-24" if h < 24 else "f) after midnight")


def section(title):
    print(f"\n--- {title} ---")


def study(name):
    M = tape.load(name)
    print(f"\n================ {name}: {len(M)} markets ================")
    U = {}
    for p, (do, h) in PLACES.items():
        U[("fav", p)] = exp.favourite_decisions(M, do, h)
        U[("generic", p)] = exp.all_decisions(M, do, h)

    section("1. Fill realism (3c under ask, held to close)")
    for p in PLACES:
        D = U[("fav", p)]
        print(f" fav, placed {p}:")
        print(exp.fmt("pay the ask", exp.summarize(exp.run(D, off=0))))
        for rule, Q, lab in [("touch", 0, "touch (first in line)"), ("queue", 100, "behind 100 contracts"),
                             ("queue", 500, "behind 500 contracts"), ("through", 0, "through (traded below us)")]:
            print(exp.fmt(lab, exp.summarize(exp.run(D, off=3, rule=rule, Q=Q))))

    section("2. Are late fills bad? Return of filled orders by local time of fill (3c, through)")
    for u in ("fav", "generic"):
        for p in PLACES:
            print(f" {u}, placed {p}:")
            R = exp.detail(U[(u, p)], off=3)
            for k, s in exp.group_ret(R, lambda r: fill_window(r["fill_h"])).items():
                print(exp.fmt(k, s))

    section("3. When to cancel an unfilled order (3c, through, unfilled = no bet)")
    cancels = [("9 AM", ("abs", 0, 9)), ("11 AM", ("abs", 0, 11)), ("noon", ("abs", 0, 12)),
               ("1 PM", ("abs", 0, 13)), ("3 PM", ("abs", 0, 15)), ("never (close)", ("close",))]
    for u in ("fav", "generic"):
        for p in PLACES:
            print(f" {u}, placed {p}:")
            print(exp.fmt("pay the ask", exp.summarize(exp.run(U[(u, p)], off=0))))
            for lab, c in cancels:
                print(exp.fmt(f"cancel at {lab}", exp.summarize(exp.run(U[(u, p)], off=3, rule="through", cancel=c))))
            print(exp.fmt("cancel noon, then pay the ask", exp.summarize(
                exp.run(U[(u, p)], off=3, rule="through", cancel=("abs", 0, 12), fallback="cross"))))

    section("4. Limit price (through, cancel at noon)")
    prices = [("ask - 1c", lambda x: x["ask"] - .01), ("ask - 2c", lambda x: x["ask"] - .02),
              ("ask - 3c", lambda x: x["ask"] - .03), ("ask - 5c", lambda x: x["ask"] - .05),
              ("bid (join best bid)", lambda x: x["bid"]), ("bid - 1c", lambda x: x["bid"] - .01),
              ("bid - 2c", lambda x: x["bid"] - .02),
              ("ask - 3c, or bid if spread>=3c", lambda x: x["bid"] if x["ask"] - x["bid"] >= .029 else x["ask"] - .03)]
    for u in ("fav", "generic"):
        for p in PLACES:
            print(f" {u}, placed {p}:")
            for lab, f in prices:
                print(exp.fmt(lab, exp.summarize(exp.run(U[(u, p)], price=f, rule="through", cancel=("abs", 0, 12)))))
    print(" by spread at placement (generic, both times, ask-3c, cancel noon):")
    G = U[("generic", "6 PM day before")] + U[("generic", "7 AM")]
    for sp in (0.01, 0.02, 0.03):
        sub = [x for x in G if (round(x["ask"] - x["bid"], 2) == sp if sp < .03 else x["ask"] - x["bid"] >= .029)]
        print(exp.fmt(f"spread {'>=' if sp >= .03 else ''}{sp:.2f}: pay ask", exp.summarize(exp.run(sub, off=0))))
        print(exp.fmt(f"spread {'>=' if sp >= .03 else ''}{sp:.2f}: ask-3c", exp.summarize(
            exp.run(sub, off=3, rule="through", cancel=("abs", 0, 12)))))

    section("5. When to place (fav, 3c under ask, through, cancel at noon; quotes rebuilt from trades)")
    for lab, (do, h) in [("noon day before", (-1, 12)), ("3 PM day before", (-1, 15)), ("6 PM day before", (-1, 18)),
                         ("9 PM day before", (-1, 21)), ("midnight", (0, 0)), ("4 AM", (0, 4)), ("7 AM", (0, 7)),
                         ("9 AM", (0, 9)), ("11 AM", (0, 11))]:
        D = exp.favourite_decisions(M, do, h)
        c = ("abs", 0, 12) if (do, h) < (0, 12) else ("rel", 1)
        print(exp.fmt(f"{lab}: pay ask", exp.summarize(exp.run(D, off=0))))
        print(exp.fmt(f"{lab}: limit", exp.summarize(exp.run(D, off=3, rule="through", cancel=c))))


if __name__ == "__main__":
    for n in sys.argv[1:] or ["main"]:
        study(n)
        sys.stdout.flush()
