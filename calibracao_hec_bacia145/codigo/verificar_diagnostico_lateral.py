"""Pré-voo e reprodução dos controles do titular. Não roda nem calibra HEC."""
import argparse
import csv
import gzip
import hashlib
import json
from pathlib import Path

from contrato_extracao import validar_nos


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def serie(path):
    values = {}
    duplicates = 0
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            key = (row["node"], int(row["time_value"]))
            q = float(row["flow"])
            if key in values:
                if values[key] != q:
                    raise ValueError(f"Duplicata conflitante em {path.name}: {key}")
                duplicates += 1
            values[key] = q
    return values, duplicates


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--referencia-pedido", type=Path, required=True)
    ap.add_argument("--titular", type=Path, required=True)
    ap.add_argument("--saida", type=Path, required=True)
    ap.add_argument("--resultados", type=Path)
    ap.add_argument("--referencia-series", type=Path)
    a = ap.parse_args()
    pedido = a.root / "rodadas/PEDIDO.json"
    p = read(pedido)
    ref = read(a.referencia_pedido)
    titular = read(a.titular)
    assert len(p["candidatos"]) == 1, "Não é busca de parâmetros"
    candidate = p["candidatos"][0]
    assert candidate["p"] == ref["candidatos"][0]["p"] == titular["p_lrdcf"], "Parâmetros diferentes do titular"
    assert candidate["rota"] == ref["candidatos"][0]["rota"] == titular["rota"] == "mc"
    assert p["papeis"] == ref["papeis"], "Papéis alterados"
    assert p["forcamento"] == "forcamento_v3b"
    sims = p["janelas"].split(",")
    assert len(set(sims)) == len(sims)
    assert all(s in ref["janelas"].split(",") for s in sims)
    assert not set(sims) & {"X20260918", "X75", "X76"}
    basin = (a.root / "dados/basin/a00_E27.basin").read_text(encoding="utf-8")
    validar_nos(p["nos_extra"], basin)
    out = {"status": "preflight_ok", "pedido_sha256": sha(pedido),
           "titular": "pc-f8-c025", "referencia": "pp-val-c000", "comparacoes": [], "chuva": {}}
    for sim in sims:
        rain_file = a.root / "dados" / p["forcamento"] / (sim + ".json.gz")
        rain_bytes = gzip.decompress(rain_file.read_bytes())
        rain = json.loads(rain_bytes)
        assert len(rain["chuva_por_subbacia"]) == 145
        assert all(len(v) == len(rain["horas"]) for v in rain["chuva_por_subbacia"].values())
        out["chuva"][sim] = {"arquivo_sha256": sha(rain_file), "conteudo_sha256": hashlib.sha256(rain_bytes).hexdigest()}
        if a.resultados:
            assert a.referencia_series
            files = list(a.resultados.rglob(f"{candidate['id']}/{sim}/vazao.csv"))
            baselines = list(a.referencia_series.rglob(f"pp-val-c000/{sim}/vazao.csv"))
            assert len(files) == len(baselines) == 1, f"Saída/referência ausente ou ambígua: {sim}"
            actual, dup_a = serie(files[0])
            expected, dup_b = serie(baselines[0])
            assert dup_a == 0
            extras_presentes = sorted(set(n for n, t in actual) & set(p["nos_extra"]))
            assert set(extras_presentes) == set(p["nos_extra"])
            metadata = read(files[0].with_name("series_metadata.json"))
            assert {m["node"] for m in metadata} == {n for n, t in actual}
            for m in metadata:
                assert m["units"].upper() in {"CMS", "M3/S"}, m
                assert m["type"] in {"INST-VAL", "PER-AVER"}, m
                assert m["interval"] == 10, m
                assert m["pathname"].startswith("//" + m["node"] + "/FLOW/"), m
            for node in {n for n, t in actual}:
                assert sum(m["count"] for m in metadata if m["node"] == node) == sum(k[0] == node for k in actual)
            assert set(expected) <= set(actual)
            nodes = {n for n, t in expected}
            assert {k for k in actual if k[0] in nodes} == set(expected)
            delta = max(abs(actual[k] - v) for k, v in expected.items())
            assert delta <= 1e-6, f"Controle mudou: {sim}, delta={delta}"
            meta = read(files[0].with_name("extracao.json"))
            assert meta["chuva_json_sha256"] == out["chuva"][sim]["conteudo_sha256"]
            assert meta["vazao_sha256"] == sha(files[0])
            assert meta["origem"]["pedido"] == p
            assert meta["origem"]["catalogo_sha256"] == sha(a.root / "dados/catalogo_ampliado.json")
            for old in ("bacia_inteira.py", "estrutura_v3.py", "comum.py"):
                assert (a.root / "codigo" / old).exists()
            out["comparacoes"].append({"sim": sim, "pares_controle": len(expected),
                                       "duplicatas_identicas_referencia": dup_b,
                                       "max_abs_diff_m3s": delta, "nos_extra_presentes": extras_presentes,
                                       "series_metadata": metadata,
                                       "manifesto": meta, "referencia_sha256": sha(baselines[0])})
    if a.resultados:
        out["status"] = "reproducao_controles_confirmada"
    a.saida.parent.mkdir(parents=True, exist_ok=True)
    a.saida.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"status": out["status"], "janelas": sims,
                      "deltas": [v["max_abs_diff_m3s"] for v in out["comparacoes"]]}))


if __name__ == "__main__":
    main()
