# -*- coding: utf-8 -*-
"""Base viária da SEMA (Base Cartográfica Vetorial Contínua do RS, 1:25.000 — BCRS25, publicada
pela FEPAM em http://ww2.fepam.rs.gov.br/bcrs25/) recortada para Santa Tereza e Muçum, para
comparar com a rede do OpenStreetMap dos painéis (comparar_vias.py).

  python codigo_python/09_rota_fuga/vias_sema.py baixar /tmp/sema        # acha e baixa os .zip de transporte
  python codigo_python/09_rota_fuga/vias_sema.py recortar /tmp/sema/*.shp  # grava sema_bcrs25_vias_<cidade>.geojson

O site do estado não responde fora do Brasil; aí vale a cópia do Internet Archive (Wayback).
Recortar precisa de pyogrio e pyproj (não estão no CI enxuto).
"""
import hashlib
import json
import os
import re
import sys
import urllib.parse
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import baixar_mancha_mup as bm  # noqa: E402

BASE = "http://ww2.fepam.rs.gov.br/bcrs25/"
VIAS = re.compile(r"transp|rodov|vi[aá]rio|via_|vias|arruam|logradouro|estrad|caminho", re.I)


def lista(url, nivel=2, vistos=None):
    """Links de arquivos do índice (até `nivel` pastas abaixo), também pela cópia do Wayback."""
    vistos = vistos if vistos is not None else set()
    if url in vistos or nivel < 0:
        return []
    vistos.add(url)
    for tentativa in (url, "https://web.archive.org/web/2026id_/" + url):
        try:
            s, final = bm.baixa(tentativa, 90)
            break
        except Exception as e:  # noqa: BLE001
            print(f"  índice indisponível ({tentativa}): {e}")
    else:
        return []
    out = []
    for href in re.findall(r'href="([^"?#]+)"', s.decode("utf-8", "replace"), re.I):
        u = urllib.parse.urljoin(url, href)
        u = re.sub(r"^https?://web\.archive\.org/web/\d+(id_)?/", "", u)
        if "fepam.rs.gov.br/bcrs25" not in u:
            continue
        if u.endswith("/") and len(u) > len(url):
            out += lista(u, nivel - 1, vistos)
        elif not u.endswith("/"):
            out.append(u)
    return out


def baixar(destino):
    os.makedirs(destino, exist_ok=True)
    arquivos = sorted(set(lista(BASE)))
    for u in arquivos:
        print("ARQUIVO:", u)
    alvos = [u for u in arquivos if u.lower().endswith((".zip", ".rar", ".7z")) and VIAS.search(urllib.parse.unquote(u))]
    print("alvos:", alvos)
    origem = []
    for u in alvos:
        for tentativa in (u, "https://web.archive.org/web/2id_/" + u):
            try:
                dados, final = bm.baixa(tentativa, 900)
            except Exception as e:  # noqa: BLE001
                print(f"falhou {tentativa}: {e}")
                continue
            if dados[:2] != b"PK":
                print(f"não é zip: {final}")
                continue
            nome = os.path.basename(urllib.parse.unquote(urllib.parse.urlparse(u).path))
            with open(os.path.join(destino, nome), "wb") as f:
                f.write(dados)
            zipfile.ZipFile(os.path.join(destino, nome)).extractall(os.path.join(destino, os.path.splitext(nome)[0]))
            origem.append({"arquivo": u, "baixado_de": final, "sha256": hashlib.sha256(dados).hexdigest(), "bytes": len(dados)})
            print(f"OK {nome}: {len(dados) / 1e6:.1f} MB")
            break
    with open(os.path.join(destino, "origem.json"), "w", encoding="utf-8") as f:
        json.dump(origem, f, ensure_ascii=False, indent=1)
    return 0 if origem else 1


def recortar(arquivos):
    import pyogrio
    import shapely
    from pyproj import CRS, Transformer
    import preparar_mancha
    import pontos_encontro as pe
    for cidade in pe.CIDADES:
        caixa = preparar_mancha.caixa_lonlat([cidade])
        feats = []
        for arq in arquivos:
            info = pyogrio.read_info(arq)
            if "Line" not in (info.get("geometry_type") or ""):
                print(f"{os.path.basename(arq)}: {info.get('geometry_type')} (não é linha), fica de fora")
                continue
            crs = info.get("crs")
            geo = not crs or CRS.from_user_input(crs).is_geographic
            bbox = caixa
            if not geo:
                inv = Transformer.from_crs(4326, CRS.from_user_input(crs), always_xy=True)
                xs, ys = inv.transform([caixa[0], caixa[2]], [caixa[1], caixa[3]])
                bbox = (min(xs), min(ys), max(xs), max(ys))
            _m, _f, geoms, campos = pyogrio.raw.read(arq, read_geometry=True, bbox=bbox)
            nomes = list(info["fields"])
            tr = None if geo else Transformer.from_crs(CRS.from_user_input(crs), 4326, always_xy=True)
            for i, g in enumerate(geoms):
                if g is None:
                    continue
                gg = shapely.from_wkb(g)
                if tr:
                    gg = shapely.transform(gg, lambda c: __import__("numpy").column_stack(tr.transform(c[:, 0], c[:, 1])))
                props = {n: (v[i].item() if hasattr(v[i], "item") else v[i]) for n, v in zip(nomes, campos)}
                props = {k: (str(v) if not isinstance(v, (int, float, str, type(None))) else v) for k, v in props.items()}
                props["_camada"] = os.path.basename(arq)
                feats.append({"type": "Feature", "geometry": shapely.geometry.mapping(gg), "properties": props})
            print(f"{cidade}: {os.path.basename(arq)} · {len(geoms)} linhas perto · CRS {crs}")
        saida = os.path.join(pe.DADOS, f"sema_bcrs25_vias_{cidade}.geojson")
        with open(saida, "w", encoding="utf-8") as f:
            json.dump({"type": "FeatureCollection", "fonte": "SEMA/FEPAM, BCRS25 1:25.000 (" + BASE + ")",
                       "features": feats}, f, ensure_ascii=False, separators=(",", ":"))
        print(f"{cidade}: {os.path.relpath(saida, pe.RAIZ)} ({len(feats)} linhas, {os.path.getsize(saida) / 1e3:.0f} kB)")


if __name__ == "__main__":
    if sys.argv[1:2] == ["baixar"]:
        sys.exit(baixar(sys.argv[2] if len(sys.argv) > 2 else "/tmp/sema"))
    if sys.argv[1:2] == ["recortar"]:
        recortar(sys.argv[2:])
    else:
        print(__doc__)
