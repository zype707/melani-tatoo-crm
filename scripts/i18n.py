"""Traducciones sin abrir el .po entero (≈6000 líneas).

  python scripts/i18n.py extraer      # makemessages (django + djangojs) y lista lo pendiente
  python scripts/i18n.py pendientes   # entradas sin traducir o fuzzy, una por línea (JSON)
  python scripts/i18n.py aplicar f.tsv  # aplica "msgid<TAB>traducción" (plural: "uno||varios") y compila
  python scripts/i18n.py buscar texto # busca un msgid y muestra su traducción

Requiere gettext (msgfmt/xgettext) y polib (requirements-dev.txt).
"""

import json
import subprocess
import sys
from pathlib import Path

import polib

RAIZ = Path(__file__).resolve().parent.parent
PO = {
    "django": RAIZ / "locale/en/LC_MESSAGES/django.po",
    "djangojs": RAIZ / "locale/en/LC_MESSAGES/djangojs.po",
}
IGNORAR = ["-i", "staticfiles/*", "-i", "*/tests/*", "-i", "scripts/*", "-i", "media_privado/*", "-i", "*/management/*"]


def manage(*args):
    subprocess.run(
        [sys.executable, "manage.py", *args],
        cwd=RAIZ,
        check=True,
        env={**__import__("os").environ, "DJANGO_SETTINGS_MODULE": "estudio.settings.dev"},
    )


def pendientes():
    salida = []
    for dominio, ruta in PO.items():
        for e in polib.pofile(str(ruta)):
            vacio = not e.msgstr_plural.get(0) if e.msgid_plural else not e.msgstr
            if vacio or "fuzzy" in e.flags:
                salida.append(
                    {
                        "dominio": dominio,
                        "msgid": e.msgid,
                        "plural": e.msgid_plural or None,
                        "fuzzy": "fuzzy" in e.flags,
                    }
                )
    return salida


def aplicar(tsv: Path):
    tr = {}
    for linea in tsv.read_text(encoding="utf-8").splitlines():
        if "\t" in linea:
            k, v = linea.split("\t", 1)
            tr[k.replace("\\n", "\n")] = v.replace("\\n", "\n")
    hechos = 0
    for ruta in PO.values():
        po = polib.pofile(str(ruta))
        for e in po:
            if e.msgid in tr:
                v = tr[e.msgid]
                if e.msgid_plural:
                    uno, _, varios = v.partition("||")
                    e.msgstr_plural = {0: uno, 1: varios or uno}
                else:
                    e.msgstr = v
                if "fuzzy" in e.flags:
                    e.flags.remove("fuzzy")
                e.previous_msgid = None
                e.previous_msgid_plural = None
                e.previous_msgctxt = None
                hechos += 1
        po.save()
    manage("compilemessages", "-v0")
    print(f"{hechos} entradas aplicadas y compiladas. Pendientes: {len(pendientes())}")


def main():
    orden = sys.argv[1] if len(sys.argv) > 1 else "pendientes"
    if orden == "extraer":
        manage("makemessages", "-l", "en", "--no-obsolete", *IGNORAR)
        manage(
            "makemessages",
            "-d",
            "djangojs",
            "-l",
            "en",
            "--no-obsolete",
            "-i",
            "staticfiles/*",
            "-i",
            "static/vendor/*",
        )
        orden = "pendientes"
    if orden == "pendientes":
        for p in pendientes():
            print(json.dumps(p, ensure_ascii=False))
    elif orden == "aplicar":
        aplicar(Path(sys.argv[2]))
    elif orden == "buscar":
        texto = sys.argv[2].lower()
        for ruta in PO.values():
            for e in polib.pofile(str(ruta)):
                if texto in e.msgid.lower():
                    print(json.dumps({"msgid": e.msgid, "msgstr": e.msgstr or e.msgstr_plural}, ensure_ascii=False))
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
