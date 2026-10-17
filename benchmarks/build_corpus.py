"""Generate the offline extraction corpus under ``tests/corpus``.

Each case is a news listing page built from a common CMS layout and a language,
with the items a person would label as the news list (title, link, date).
Real site snapshots are not committed because their content is third-party
copyright; the layouts reproduce structures seen on real sites instead.

Run from the repository root:  python benchmarks/build_corpus.py
"""

from __future__ import annotations

import datetime as dt
import html
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "tests" / "corpus"
BASE = "https://news.example.org"

MONTHS = {
    "en": "January February March April May June July August September October November December",
    "ru": "января февраля марта апреля мая июня июля августа сентября октября ноября декабря",
    "de": "Januar Februar März April Mai Juni Juli August September Oktober November Dezember",
    "fr": "janvier février mars avril mai juin juillet août septembre octobre novembre décembre",
    "es": "enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre",
    "it": "gennaio febbraio marzo aprile maggio giugno luglio agosto settembre ottobre novembre dicembre",
    "pt": "janeiro fevereiro março abril maio junho julho agosto setembro outubro novembro dezembro",
    "uk": "січня лютого березня квітня травня червня липня серпня вересня жовтня листопада грудня",
}

WORDS = {
    "en": (
        "Council approves new budget for regional transport projects|Researchers publish annual report on coastal water quality|"
        "City opens public consultation on the future of the harbour|Ministry announces grants for small business innovation|"
        "University launches open data portal for climate records|Agency updates guidance on digital service standards|"
        "Board appoints new director for the national statistics office|Library extends opening hours during the exam season"
    ),
    "ru": (
        "Совет утвердил новый бюджет региональных транспортных проектов|Исследователи опубликовали годовой отчёт о качестве воды|"
        "Город открыл общественное обсуждение будущего порта|Министерство объявило гранты для малого бизнеса|"
        "Университет запустил портал открытых климатических данных|Агентство обновило рекомендации по цифровым услугам|"
        "Правление назначило нового директора статистической службы|Библиотека продлила часы работы на время сессии"
    ),
    "de": (
        "Rat genehmigt neuen Haushalt für regionale Verkehrsprojekte|Forscher veröffentlichen Jahresbericht zur Wasserqualität|"
        "Stadt startet öffentliche Beteiligung zur Zukunft des Hafens|Ministerium kündigt Förderung für kleine Unternehmen an|"
        "Universität startet offenes Datenportal für Klimadaten|Behörde aktualisiert Leitfaden für digitale Dienste|"
        "Vorstand ernennt neue Leitung des Statistikamts|Bibliothek verlängert Öffnungszeiten während der Prüfungszeit"
    ),
    "fr": (
        "Le conseil approuve un nouveau budget pour les transports régionaux|Des chercheurs publient le rapport annuel sur la qualité de l’eau|"
        "La ville ouvre une consultation publique sur l’avenir du port|Le ministère annonce des subventions pour les petites entreprises|"
        "L’université lance un portail de données ouvertes sur le climat|L’agence met à jour ses recommandations numériques|"
        "Le conseil nomme une nouvelle direction pour l’institut statistique|La bibliothèque prolonge ses horaires pendant les examens"
    ),
    "es": (
        "El consejo aprueba un nuevo presupuesto para el transporte regional|Investigadores publican el informe anual sobre la calidad del agua|"
        "La ciudad abre una consulta pública sobre el futuro del puerto|El ministerio anuncia ayudas para pequeñas empresas|"
        "La universidad lanza un portal de datos abiertos sobre el clima|La agencia actualiza su guía de servicios digitales|"
        "La junta nombra una nueva dirección para la oficina de estadística|La biblioteca amplía su horario durante los exámenes"
    ),
    "it": (
        "Il consiglio approva il nuovo bilancio per i trasporti regionali|I ricercatori pubblicano il rapporto annuale sulla qualità dell’acqua|"
        "La città apre una consultazione pubblica sul futuro del porto|Il ministero annuncia contributi per le piccole imprese|"
        "L’università lancia un portale di dati aperti sul clima|L’agenzia aggiorna le linee guida sui servizi digitali|"
        "Il consiglio nomina una nuova direzione per l’istituto di statistica|La biblioteca estende gli orari durante gli esami"
    ),
    "pt": (
        "Conselho aprova novo orçamento para projetos de transporte regional|Pesquisadores publicam relatório anual sobre a qualidade da água|"
        "Cidade abre consulta pública sobre o futuro do porto|Ministério anuncia apoio para pequenas empresas|"
        "Universidade lança portal de dados abertos sobre o clima|Agência atualiza orientações sobre serviços digitais|"
        "Conselho nomeia nova direção para o instituto de estatística|Biblioteca amplia horário durante a época de exames"
    ),
    "uk": (
        "Рада затвердила новий бюджет регіональних транспортних проєктів|Дослідники оприлюднили річний звіт про якість води|"
        "Місто відкрило громадське обговорення майбутнього порту|Міністерство оголосило гранти для малого бізнесу|"
        "Університет запустив портал відкритих кліматичних даних|Агенція оновила рекомендації щодо цифрових послуг|"
        "Правління призначило нового директора статистичної служби|Бібліотека подовжила години роботи під час сесії"
    ),
}


def date_text(lang: str, value: dt.date, style: str) -> str:
    month = MONTHS[lang].split()[value.month - 1]
    if style == "iso":
        return value.isoformat()
    if style == "dotted":
        return value.strftime("%d.%m.%Y")
    if style == "slashed":
        return value.strftime("%d/%m/%Y")
    if lang == "en":
        return (
            f"{month} {value.day}, {value.year}" if style == "long" else value.strftime("%d %b %Y")
        )
    if lang == "de":
        return f"{value.day}. {month} {value.year}"
    if lang in ("es", "pt"):
        return f"{value.day} de {month} de {value.year}"
    return f"{value.day} {month} {value.year}"


def items_for(lang: str, seed: int, count: int = 6):
    rng = random.Random(seed)
    titles = WORDS[lang].split("|")
    rng.shuffle(titles)
    start = dt.date(2025, 10, 16) - dt.timedelta(days=rng.randint(0, 120))
    items = []
    for index in range(count):
        day = start - dt.timedelta(days=index * rng.randint(1, 4))
        slug = f"/{lang}/news/{seed}-{index + 1}"
        items.append(
            {"title": titles[index % len(titles)], "link": BASE + slug, "path": slug, "date": day}
        )
    return items


def esc(text: str) -> str:
    return html.escape(text, quote=True)


NAV = """<header><nav class="menu"><ul><li><a href="/">Home</a></li><li><a href="/about">About</a></li>
<li><a href="/contact">Contact</a></li></ul></nav></header>"""
FOOTER = """<footer><p>© 2025 Example Agency. Last updated 01.09.2025.</p></footer>"""


def layout_wordpress(lang, items, style):
    body = "".join(
        f"""<article class="post type-post"><header class="entry-header"><h2 class="entry-title">
<a href="{it["path"]}" rel="bookmark">{esc(it["title"])}</a></h2>
<div class="entry-meta"><time class="entry-date published" datetime="{it["date"].isoformat()}T09:00:00+00:00">
{date_text(lang, it["date"], style)}</time></div></header>
<div class="entry-summary"><p>{esc(it["title"])}. Read the full announcement for details.</p></div></article>"""
        for it in items
    )
    return f'<main id="main" class="site-main">{body}</main>'


def layout_drupal(lang, items, style):
    rows = "".join(
        f"""<div class="views-row"><div class="views-field views-field-created">
<span class="field-content">{date_text(lang, it["date"], style)}</span></div>
<div class="views-field views-field-title"><span class="field-content"><a href="{it["path"]}">{esc(it["title"])}</a></span></div></div>"""
        for it in items
    )
    return f'<div class="view view-news"><div class="view-content">{rows}</div></div>'


def layout_cards(lang, items, style):
    cards = "".join(
        f"""<div class="col-md-4"><div class="card"><img class="card-img-top" src="/img/{i}.jpg" alt="">
<div class="card-body"><h5 class="card-title"><a href="{it["path"]}">{esc(it["title"])}</a></h5>
<p class="card-text text-muted"><small>{date_text(lang, it["date"], style)}</small></p></div></div></div>"""
        for i, it in enumerate(items)
    )
    return f'<div class="container"><div class="row">{cards}</div></div>'


def layout_table(lang, items, style):
    rows = "".join(
        f"""<tr><td class="date">{date_text(lang, it["date"], style)}</td>
<td><a href="{it["path"]}">{esc(it["title"])}</a></td></tr>"""
        for it in items
    )
    return f'<table class="news"><thead><tr><th>Date</th><th>Title</th></tr></thead><tbody>{rows}</tbody></table>'


def layout_list(lang, items, style):
    rows = "".join(
        f"""<li><span class="date">{date_text(lang, it["date"], style)}</span>
<a href="{it["path"]}">{esc(it["title"])}</a></li>"""
        for it in items
    )
    return f'<ul class="news-list">{rows}</ul>'


def layout_date_after(lang, items, style):
    rows = "".join(
        f"""<div class="news-item"><h3><a class="title" href="{it["path"]}">{esc(it["title"])}</a></h3>
<div class="meta">{date_text(lang, it["date"], style)}</div><p>{esc(it["title"])}: summary of the announcement.</p></div>"""
        for it in items
    )
    return f'<section class="news">{rows}</section>'


def layout_with_sidebar(lang, items, style):
    main = layout_list(lang, items, style)
    side = "".join(
        f"""<li><a href="/{lang}/events/{i}">Event {i + 1}</a> <span>{date_text(lang, dt.date(2025, 11, 2 + i), style)}</span></li>"""
        for i in range(2)
    )
    return (
        f'<div class="layout"><main>{main}</main>'
        f'<aside class="sidebar"><h4>Events</h4><ul class="events">{side}</ul></aside></div>'
    )


def layout_category_first(lang, items, style):
    """A category link precedes the headline link (issue #19)."""
    rows = "".join(
        f"""<div class="item"><a class="category" href="/{lang}/topics/{i % 3}">Topic {i % 3}</a>
<h3><a href="{it["path"]}">{esc(it["title"])}</a></h3><span class="date">{date_text(lang, it["date"], style)}</span></div>"""
        for i, it in enumerate(items)
    )
    return f'<div class="items">{rows}</div>'


def layout_read_more(lang, items, style):
    """Teaser, then a "read more" link to the same article after the title."""
    rows = "".join(
        f"""<div class="teaser"><span class="date">{date_text(lang, it["date"], style)}</span>
<h4><a href="{it["path"]}">{esc(it["title"])}</a></h4><p>Short teaser text for the story.</p>
<a class="more" href="{it["path"]}">Read more</a></div>"""
        for it in items
    )
    return f'<div class="teasers">{rows}</div>'


def layout_with_time(lang, items, style):
    """Date and clock time, plus a comment counter with numbers."""
    rows = "".join(
        f"""<li class="entry"><div class="stamp">{date_text(lang, it["date"], style)} 14:{10 + i:02d}</div>
<a href="{it["path"]}">{esc(it["title"])}</a> <span class="comments">{3 + i} comments</span></li>"""
        for i, it in enumerate(items)
    )
    return f'<ol class="stream">{rows}</ol>'


def layout_busy_sidebar(lang, items, style):
    """The sidebar has as many dated entries as the main listing."""
    main = layout_date_after(lang, items, style)
    side = "".join(
        f"""<li><span>{date_text(lang, dt.date(2025, 11, 2 + i), style)}</span> <a href="/{lang}/events/{i}">Event {i + 1}</a></li>"""
        for i in range(len(items))
    )
    return (
        f'<div class="layout"><main>{main}</main>'
        f'<aside class="sidebar"><h4>Upcoming events</h4><ul class="events">{side}</ul></aside></div>'
    )


def layout_pager(lang, items, style):
    """A numbered pager and an archive menu of month/year links below the list."""
    listing = layout_list(lang, items, style)
    pager = "".join(f'<a href="?page={n}">{n}</a> ' for n in range(1, 6))
    archive = "".join(
        f'<li><a href="/{lang}/archive/2025/{m:02d}">{date_text(lang, dt.date(2025, m, 1), "dotted")[3:]}</a></li>'
        for m in range(1, 10)
    )
    return f'{listing}<div class="pager">{pager}</div><ul class="archive">{archive}</ul>'


def layout_flat(lang, items, style):
    """No wrapper per item: heading, date line, teaser text and a link are siblings."""
    rows = "".join(
        f"""<h2 class="news"><a href="{it["path"]}">{esc(it["title"])}</a></h2>
<div class="newsdate">Posted on <strong>{date_text(lang, it["date"], style)}</strong> by the press office</div>
{esc(it["title"])}: a short summary of the announcement for readers.
<p><a href="{it["path"]}">Read more...</a></p>"""
        for it in items
    )
    return f'<div id="content"><p class="tags"><a href="/tags/a">Tag A</a> <a href="/tags/b">Tag B</a></p>{rows}</div>'


LAYOUTS = {
    "wordpress": layout_wordpress,
    "drupal": layout_drupal,
    "cards": layout_cards,
    "table": layout_table,
    "list": layout_list,
    "date-after": layout_date_after,
    "sidebar": layout_with_sidebar,
    "category-first": layout_category_first,
    "read-more": layout_read_more,
    "with-time": layout_with_time,
    "busy-sidebar": layout_busy_sidebar,
    "pager": layout_pager,
    "flat": layout_flat,
}

STYLES = {
    "en": ["long", "short", "iso"],
    "ru": ["long", "dotted"],
    "de": ["long", "dotted"],
    "fr": ["long", "slashed"],
    "es": ["long"],
    "it": ["long"],
    "pt": ["long"],
    "uk": ["long", "dotted"],
}


def build():
    pages = ROOT / "pages"
    pages.mkdir(parents=True, exist_ok=True)
    cases = []
    seed = 0
    for lang, styles in STYLES.items():
        for style in styles:
            for layout_name, layout in LAYOUTS.items():
                seed += 1
                items = items_for(lang, seed)
                name = f"{lang}-{layout_name}-{style}"
                document = (
                    f'<!DOCTYPE html><html lang="{lang}"><head><meta charset="utf-8">'
                    f"<title>News — Example Agency</title></head><body>{NAV}"
                    f"<h1>News</h1>{layout(lang, items, style)}{FOOTER}</body></html>"
                )
                (pages / f"{name}.html").write_text(document, encoding="utf-8")
                cases.append(
                    {
                        "name": name,
                        "url": f"{BASE}/{lang}/news/",
                        "language": lang,
                        "layout": layout_name,
                        "date_style": style,
                        "page": f"pages/{name}.html",
                        "expected": [
                            {
                                "title": it["title"],
                                "link": it["link"],
                                "date": it["date"].isoformat(),
                            }
                            for it in items
                        ],
                    }
                )
    (ROOT / "cases.json").write_text(
        json.dumps({"version": 1, "cases": cases}, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(cases)} cases to {ROOT}")


if __name__ == "__main__":
    build()
