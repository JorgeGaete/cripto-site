"""Genera el sitio estático (ES/EN) con indicadores diarios de 10 criptomonedas.

    python build.py            # descarga datos (incremental, cache/) y genera site/
    python build.py --offline  # usa solo el cache

Sin servidor: el resultado (site/) se publica tal cual en GitHub Pages / Cloudflare Pages.
"""
import argparse
import json
import math
import shutil
import time
from datetime import date, datetime, timezone
from pathlib import Path

import requests
from jinja2 import Environment, FileSystemLoader

from coins import COINS
from i18n import T

ROOT = Path(__file__).resolve().parent
CACHE, OUT = ROOT / "cache", ROOT / "site"
# Dónde vive el sitio. Con dominio propio: SITE_URL = "https://midominio.com", PREFIX = ""
SITE_URL = "https://jorgegaete.github.io"
PREFIX = "/cripto-site"
BASE_URL = SITE_URL + PREFIX
# Publicidad A-Ads: IDs de los bloques creados en a-ads.com (vacío = se muestra el espacio de reserva)
AADS_TOP = ""
AADS_BOTTOM = ""  # si queda vacío se usa AADS_TOP
BINANCE = "https://data-api.binance.vision/api/v3/klines"
MONTHS = {"es": ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"],
          "en": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]}


# ---------------------------------------------------------------- datos
def get(url, params=None, tries=4):
    for i in range(tries):
        try:
            r = requests.get(url, params=params, timeout=30); r.raise_for_status(); return r.json()
        except requests.RequestException:
            if i == tries - 1: raise
            time.sleep(3 * (i + 1))


def daily(pair, offline=False):
    """[(fecha, cierre, volumen_usd)] de velas diarias CERRADAS, con cache incremental."""
    f = CACHE / f"{pair}.json"
    rows = json.loads(f.read_text()) if f.exists() else []
    if not offline:
        start = (datetime.fromisoformat(rows[-1][0]).replace(tzinfo=timezone.utc).timestamp() * 1000 + 86400000
                 if rows else 0)
        now = time.time() * 1000
        while True:
            ks = get(BINANCE, {"symbol": pair, "interval": "1d", "startTime": int(start), "limit": 1000})
            ks = [k for k in ks if k[6] < now]
            if not ks: break
            rows += [(datetime.fromtimestamp(k[0] / 1000, timezone.utc).strftime("%Y-%m-%d"), float(k[4]), float(k[7]))
                     for k in ks]
            start = ks[-1][0] + 86400000
            if len(ks) < 999: break
        CACHE.mkdir(exist_ok=True); f.write_text(json.dumps(rows))
    return rows


def usdclp(offline=False):
    """Dólar observado {fecha: valor} desde 2017 (mindicador.cl), cache incremental por año."""
    f = CACHE / "usdclp.json"
    d = json.loads(f.read_text()) if f.exists() else {}
    if not offline:
        y0 = 2017 if not d else int(max(d)[:4])
        for y in range(y0, date.today().year + 1):
            for x in get(f"https://mindicador.cl/api/dolar/{y}")["serie"]:
                d[x["fecha"][:10]] = x["valor"]
        f.write_text(json.dumps(dict(sorted(d.items()))))
    return dict(sorted(d.items()))


# ---------------------------------------------------------------- indicadores
def mean(x): return sum(x) / len(x)


def indicators(rows):
    d = [r[0] for r in rows]; c = [r[1] for r in rows]; v = [r[2] for r in rows]
    p = c[-1]
    ma50, ma200 = mean(c[-50:]), mean(c[-200:])
    yr = c[-365:]
    i_ath = max(range(len(c)), key=c.__getitem__)
    lr = [math.log(c[i] / c[i - 1]) for i in range(len(c) - 365, len(c))]

    def ann_vol(x): m = mean(x); return math.sqrt(sum((a - m) ** 2 for a in x) / (len(x) - 1)) * math.sqrt(365) * 100
    vol30 = ann_vol(lr[-30:])
    vol1y = mean([ann_vol(lr[i - 30:i]) for i in range(30, len(lr) + 1, 7)])
    return {
        "date": d[-1], "price": p,
        "ch24": (p / c[-2] - 1) * 100, "ch7": (p / c[-8] - 1) * 100, "ch30": (p / c[-31] - 1) * 100,
        "p30": c[-31], "d30": d[-31], "mom_pos": p > c[-31],
        "ma50": ma50, "ma200": ma200, "vs_ma50": (p / ma50 - 1) * 100, "vs_ma200": (p / ma200 - 1) * 100,
        "ath": c[i_ath], "ath_date": d[i_ath], "dd": (p / c[i_ath] - 1) * 100,
        "days_ath": (date.fromisoformat(d[-1]) - date.fromisoformat(d[i_ath])).days,
        "pct1y": round(100 * sum(x <= p for x in yr) / len(yr)), "lo1y": min(yr), "hi1y": max(yr),
        "vol30": vol30, "vol1y": vol1y, "v1": v[-1], "v30": mean(v[-31:-1]),
        "first": d[0],
        # serie para el gráfico (último año) con medias
        "chart": [(d[i], c[i], mean(c[i - 49:i + 1]), mean(c[i - 199:i + 1])) for i in range(len(c) - 365, len(c))],
    }


# ---------------------------------------------------------------- formato
def fnum(x, lang, dec=None):
    if dec is None:
        a = abs(x); dec = 0 if a >= 1000 else 2 if a >= 1 else 4 if a >= 0.01 else 6
    s = f"{x:,.{dec}f}"
    return s.replace(",", "§").replace(".", ",").replace("§", ".") if lang == "es" else s


def fbig(x, lang):
    for div, suf in ((1e9, " B" if lang == "en" else " mil M"), (1e6, " M"), (1e3, " K" if lang == "en" else " mil")):
        if x >= div: return fnum(x / div, lang, 1) + suf
    return fnum(x, lang, 0)


def fpct(x, lang, sign=True):
    return (("+" if x > 0 and sign else "") + fnum(x, lang, 1))


def ordinal(n, lang):
    if lang != "en": return str(n)
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def fdate(s, lang):
    y, m, d = map(int, s.split("-"))
    return f"{d} {MONTHS['es'][m - 1]} {y}" if lang == "es" else f"{MONTHS['en'][m - 1]} {d}, {y}"


def svg_chart(rows, lang, compact=False):
    """Gráfico SVG (sin librerías): precio, media 50 y media 200 del último año, con etiquetas directas al final.
    El crosshair/tooltip lo agrega el JS de la página leyendo data-series."""
    W, H, T, B, L, R = (380, 260, 12, 26, 52, 10) if compact else (760, 300, 16, 28, 58, 96)
    vals = [x for r in rows for x in r[1:]]
    lo, hi = min(vals), max(vals)
    pad = (hi - lo) * 0.04; lo, hi = lo - pad, hi + pad
    sx = lambda i: L + i * (W - L - R) / (len(rows) - 1)
    sy = lambda y: T + (hi - y) / (hi - lo) * (H - T - B)
    path = lambda k: "M" + " L".join(f"{sx(i):.1f},{sy(r[k]):.1f}" for i, r in enumerate(rows))
    nt = 3 if compact else 4; step = (hi - lo) / nt
    grid = "".join(f'<line x1="{L}" x2="{W - R}" y1="{sy(lo + j * step):.1f}" y2="{sy(lo + j * step):.1f}" class="grid"/>'
                   f'<text x="{L - 8}" y="{sy(lo + j * step) + 4:.1f}" text-anchor="end" class="tick">{fnum(lo + j * step, lang)}</text>'
                   for j in range(nt + 1))
    months = "".join(f'<text x="{sx(i):.1f}" y="{H - 8}" text-anchor="middle" class="tick">{MONTHS[lang][int(r[0][5:7]) - 1]}</text>'
                     for i, r in enumerate(rows) if r[0][8:] == "01" and (not compact or int(r[0][5:7]) % 2 == 1))
    names = {"es": ("Precio", "Media 50d", "Media 200d"), "en": ("Price", "50d MA", "200d MA")}[lang]
    # etiquetas directas al final de cada línea, separadas si chocan
    ends = sorted([(sy(rows[-1][k]), k) for k in (1, 2, 3)])
    ys = [e[0] for e in ends]
    for i in range(1, 3):
        if ys[i] - ys[i - 1] < 14: ys[i] = ys[i - 1] + 14
    labels = "" if compact else "".join(f'<text x="{W - R + 8}" y="{y + 4:.1f}" class="end s{k}">{names[k - 1]}</text>'
                                        for y, (_, k) in zip(ys, ends))
    data = json.dumps({"x0": L, "x1": W - R, "lo": lo, "hi": hi, "T": T, "B": B, "H": H,
                       "d": [r[0] for r in rows], "s": [[round(r[k], 6) for r in rows] for k in (1, 2, 3)],
                       "n": names}, separators=(",", ":"))
    return (f'<svg viewBox="0 0 {W} {H}" class="chart {"compact" if compact else "wide"}" role="img" aria-label="{names[0]}, {names[1]}, {names[2]}" '
            f"data-series='{data}'>{grid}{months}"
            f'<path d="{path(3)}" class="line s3"/><path d="{path(2)}" class="line s2"/><path d="{path(1)}" class="line s1"/>'
            f'{labels}<line class="xhair" x1="0" x2="0" y1="{T}" y2="{H - B}" visibility="hidden"/></svg>')


# ---------------------------------------------------------------- build
def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--offline", action="store_true"); a = ap.parse_args()
    data = {}
    for sym, pair, name, slug in COINS:
        rows = daily(pair, a.offline)
        data[sym] = {"sym": sym, "name": name, "slug": slug, "rows": rows, **indicators(rows)}
    fx = usdclp(a.offline)

    if OUT.exists(): shutil.rmtree(OUT)
    (OUT / "data").mkdir(parents=True)
    shutil.copytree(ROOT / "static", OUT / "static")
    # datos para la calculadora (cierres diarios + dólar observado)
    for s, x in data.items():
        (OUT / "data" / f"{s}.json").write_text(json.dumps({"d": [r[0] for r in x["rows"]], "c": [r[1] for r in x["rows"]]},
                                                           separators=(",", ":")))
    (OUT / "data" / "usdclp.json").write_text(json.dumps(fx, separators=(",", ":")))

    env = Environment(loader=FileSystemLoader(ROOT / "templates"), autoescape=False)
    asof = min(x["date"] for x in data.values())
    pages = []
    for lang, t in T.items():
        other = "en" if lang == "es" else "es"
        ctx = dict(P=PREFIX, ads=(AADS_TOP, AADS_BOTTOM or AADS_TOP), t=t, lang=lang, other=other, asof=fdate(asof, lang), year=asof[:4],
                   fnum=lambda x, d=None: fnum(x, lang, d), fpct=lambda x, s=True: fpct(x, lang, s),
                   fbig=lambda x: fbig(x, lang), ordinal=lambda n: ordinal(n, lang), fdate=lambda s: fdate(s, lang), coins=list(data.values()))

        def render(tpl, path, **kw):
            out = OUT / lang / path; out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(env.get_template(tpl).render(**ctx, path=path, **kw))
            pages.append(f"{lang}/{path}")

        render("index.html", "index.html")
        render("calc.html", "calculadora/index.html" if lang == "es" else "calculator/index.html")
        for x in data.values():
            dir_ = t["above"] if x["vs_ma200"] > 0 else t["below"]
            fill = dict(name=x["name"], sym=x["sym"], price=fnum(x["price"], lang), ma200=fnum(x["ma200"], lang),
                        ma50=fnum(x["ma50"], lang), pct_abs=fnum(abs(x["vs_ma200"]), lang, 1), dir=dir_,
                        mom=t["positive"] if x["mom_pos"] else t["negative"])
            render("coin.html", f"{x['slug']}/index.html", x=x, fill=fill, chart=svg_chart(x["chart"], lang) + svg_chart(x["chart"], lang, True),
                   title=t["coin_title"].format(**fill), desc=t["coin_desc"].format(**fill))
    # raíz: redirige según idioma del navegador
    (OUT / "index.html").write_text(env.get_template("root.html").render(P=PREFIX))
    (OUT / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {BASE_URL}/sitemap.xml\n")
    (OUT / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                                     + "".join(f"<url><loc>{BASE_URL}/{p.replace('index.html', '')}</loc><lastmod>{asof}</lastmod></url>"
                                               for p in pages) + "</urlset>\n")
    print(f"OK: {len(pages)} páginas en {OUT} (datos al {asof})")


if __name__ == "__main__":
    main()
