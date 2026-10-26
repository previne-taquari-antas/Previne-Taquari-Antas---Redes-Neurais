# -*- coding: utf-8 -*-
"""Baixa a área diretamente atingida 2024 (Mapa Único do Plano Rio Grande) que a FEPAM publica em
https://fepam.rs.gov.br/arquivos-geoespaciais-eventos-climaticos-de-maio-de-2024 (shapefile .zip,
SIRGAS 2000). O site do estado não responde fora do Brasil; aí vale a cópia guardada no Internet
Archive (Wayback Machine), registrada no arquivo de origem.

  python codigo_python/09_rota_fuga/baixar_mancha_mup.py /tmp/mup    # grava /tmp/mup/ada.zip e origem.txt
"""
import hashlib
import html
import json
import os
import re
import sys
import urllib.parse
import urllib.request

PAGINA = "https://fepam.rs.gov.br/arquivos-geoespaciais-eventos-climaticos-de-maio-de-2024"
CABECALHO = {"User-Agent": "Mozilla/5.0 (PREVINE; pesquisa UFRGS)"}
ARQUIVO = re.compile(r"\.(zip|rar|7z|gpkg|kmz)(\?|$)", re.I)
ADA = re.compile(r"atingid|diretamente|(^|[^a-z])ada([^a-z]|$)", re.I)


def baixa(url, limite_s):
    with urllib.request.urlopen(urllib.request.Request(url, headers=CABECALHO), timeout=limite_s) as r:
        return r.read(), r.geturl()


def links(pagina, base):
    out = []
    for m in re.finditer(r'<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>', pagina, re.S | re.I):
        texto = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", m.group(2))).split())
        u = urllib.parse.urljoin(base, m.group(1))
        u = re.sub(r"^https?://web\.archive\.org/web/\d+(id_)?/", "", u)  # link reescrito pelo Wayback
        out.append((u, texto))
    return out


def main(destino):
    os.makedirs(destino, exist_ok=True)
    candidatos = []
    for nome, url in (("FEPAM", PAGINA), ("Wayback", "https://web.archive.org/web/2026id_/" + PAGINA)):
        try:
            s, final = baixa(url, 60)
        except Exception as e:  # noqa: BLE001
            print(f"página ({nome}) indisponível: {e}")
            continue
        print(f"página ({nome}): {final}")
        for u, t in links(s.decode("utf-8", "replace"), PAGINA):
            if ARQUIVO.search(u):
                print("  LINK:", t, "->", u)
                if ADA.search(t + " " + u):
                    candidatos.append(u)
    try:  # arquivos .zip da FEPAM que o Wayback guardou
        cdx, _ = baixa("https://web.archive.org/cdx/search/cdx?url=fepam.rs.gov.br/upload/arquivos/&matchType=prefix"
                       "&output=json&collapse=urlkey&limit=5000", 180)
        for linha in json.loads(cdx or b"[]")[1:]:
            ts, original, status = linha[1], linha[2], linha[4]
            if ARQUIVO.search(original):
                print("  CDX:", ts, status, original)
                if ADA.search(original):
                    candidatos.append(original)
    except Exception as e:  # noqa: BLE001
        print("CDX do Wayback indisponível:", e)
    candidatos = list(dict.fromkeys(candidatos))
    print("candidatos:", candidatos)
    for u in candidatos:
        for url in (u, "https://web.archive.org/web/2id_/" + u):
            try:
                dados, final = baixa(url, 900)
            except Exception as e:  # noqa: BLE001
                print(f"falhou {url}: {e}")
                continue
            if dados[:2] != b"PK":
                print(f"não é zip: {final} ({len(dados)} bytes)")
                continue
            with open(os.path.join(destino, "ada.zip"), "wb") as f:
                f.write(dados)
            sha = hashlib.sha256(dados).hexdigest()
            with open(os.path.join(destino, "origem.txt"), "w", encoding="utf-8") as f:
                f.write(f"Arquivo: {u}\nBaixado de: {final}\nsha256: {sha}\nbytes: {len(dados)}\n")
            print(f"OK: {final} ({len(dados) / 1e6:.1f} MB, sha256 {sha})")
            return 0
    print("não consegui baixar a área diretamente atingida")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "/tmp/mup"))
