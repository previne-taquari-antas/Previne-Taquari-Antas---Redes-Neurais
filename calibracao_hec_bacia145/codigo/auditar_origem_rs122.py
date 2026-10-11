"""Confronta CSV com XML ANA bruto arquivado; não baixa nem corrige dados.

Igualdade comprova a transcrição, não independência da vazão ou validade de curva-chave.
"""
import argparse
import csv
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def verificar(xml, csv_path):
    raw, duplicates, conflicts, station_codes = {}, 0, [], set()
    for row in ET.parse(xml).getroot().iter():
        if row.tag.split("}")[-1] != "DadosHidrometereologicos":
            continue
        fields = {x.tag.split("}")[-1]: (x.text or "").strip() for x in row}
        if "DataHora" not in fields:
            continue
        station_codes.add(fields.get("CodEstacao"))
        key = fields["DataHora"]
        values = [fields.get(k, "") for k in ("Nivel", "Vazao", "Chuva")]
        if key in raw:
            duplicates += 1
            if values != raw[key]:
                conflicts.append(key)
        raw[key] = values
    parsed, csv_dups = {}, []
    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            key = r["data_hora"].strip()
            if key in parsed:
                csv_dups.append(key)
            parsed[key] = [r[k].strip() for k in ("nivel_cm", "vazao_m3s", "chuva_mm")]
    mismatches = [t for t in sorted(set(raw) | set(parsed)) if raw.get(t) != parsed.get(t)]
    ok = not conflicts and not csv_dups and not mismatches and station_codes == {"86298000"} and bool(raw)
    return {"status": "transcricao_confirmada" if ok else "falha", "n": len(raw),
            "postos_xml": sorted(station_codes), "duplicatas_xml": duplicates,
            "conflitos_xml": conflicts, "duplicatas_csv": csv_dups, "divergencias": mismatches,
            "vazoes_preenchidas": sum(bool(v[1]) for v in raw.values()),
            "xml": str(xml), "xml_sha256": sha(xml), "csv": str(csv_path), "csv_sha256": sha(csv_path)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dados", type=Path, required=True)
    ap.add_argument("--saida", type=Path, required=True)
    a = ap.parse_args()
    rows = [{"janela": sim, **verificar(a.dados / "xml" / f"86298000_{sim}.xml",
                                      a.dados / "csv" / f"86298000_{sim}.csv")}
            for sim in ("S2023_07", "S2023_11")]
    out = {"fonte": "ANA DadosHidrometeorologicos; campo Vazao do XML arquivado", "resultados": rows,
           "codigo_sha256": sha(Path(__file__)),
           "limites": ["Não consultada nova versão da API", "CSV não contém metadados de curva-chave ou medição",
                       "Vazão telemétrica publicada não equivale a medição independente validada"]}
    a.saida.parent.mkdir(parents=True, exist_ok=True)
    if a.saida.exists():
        raise ValueError("Preservar saída anterior")
    a.saida.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps([{k: v for k, v in r.items() if k not in {"xml", "csv"}} for r in rows]))
    if any(r["status"] != "transcricao_confirmada" for r in rows):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
