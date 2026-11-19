"""Arquivo permanente das previsoes ao vivo (Santa Tereza e Muçum).

Os robos mantem em ``historico_previsoes_ao_vivo*.json`` apenas os ultimos
1.200 registros (cerca de 2 a 3 semanas). Este script copia cada registro para
um arquivo mensal permanente, sem nunca apagar nada, para que a avaliacao
prospectiva por evento (gate da agenda ``rna-multi-horizonte``) nao perca a
evidencia antiga.

Regras:
- chave = ``id`` do registro (local|horizonte|modelo|hora_modelo);
- mes do arquivo = mes de ``hora_modelo``;
- enquanto o registro esta no historico rolante, a versao do robo e a mais
  nova e substitui a arquivada (inclusive reconferencias);
- quando sai do historico rolante, o registro fica congelado no arquivo;
- registros que ja nao estao no historico rolante nunca sao removidos.

Uso:
    python -B scripts/arquivar_historico_ao_vivo.py              # os dois locais
    python -B scripts/arquivar_historico_ao_vivo.py --local mucum
    python -B scripts/arquivar_historico_ao_vivo.py --entrada X.json --local santa_tereza

Somente biblioteca padrao. Pesquisa; nao e alerta oficial.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
DESTINO = RAIZ / "assets" / "data" / "historico_ao_vivo_arquivo"
SCHEMA = "previne_historico_ao_vivo_arquivo_v1"

FONTES = {
    "santa_tereza": RAIZ / "historico_previsoes_ao_vivo.json",
    "mucum": RAIZ / "historico_previsoes_ao_vivo_mucum.json",
}

_MES = re.compile(r"^(\d{4})-(\d{2})-\d{2}T")


def mes_do_registro(reg: dict) -> str | None:
    m = _MES.match(str(reg.get("hora_modelo") or ""))
    return f"{m.group(1)}-{m.group(2)}" if m else None


def chave_ordem(reg: dict):
    return (
        str(reg.get("hora_modelo") or ""),
        str(reg.get("horizonte") or ""),
        str(reg.get("modelo") or ""),
    )


def ler_registros(caminho: Path) -> list[dict]:
    with open(caminho, "r", encoding="utf-8") as f:
        dados = json.load(f)
    regs = dados.get("registros") if isinstance(dados, dict) else dados
    if not isinstance(regs, list):
        raise ValueError(f"{caminho}: sem lista 'registros'")
    return [r for r in regs if isinstance(r, dict) and r.get("id")]


def carregar_mes(caminho: Path) -> dict[str, dict]:
    if not caminho.exists():
        return {}
    with open(caminho, "r", encoding="utf-8") as f:
        dados = json.load(f)
    return {r["id"]: r for r in dados.get("registros", []) if r.get("id")}


def escrever_mes(caminho: Path, local: str, mes: str, regs: dict[str, dict]) -> bool:
    ordenados = sorted(regs.values(), key=chave_ordem)
    dados = {
        "schema_version": SCHEMA,
        "local": local,
        "mes": mes,
        "aviso": "Pesquisa. Registro permanente das previsoes ao vivo; nao e alerta oficial.",
        "total": len(ordenados),
        "registros": ordenados,
    }
    # Um registro por linha: compacto e com diffs legiveis no git.
    cabecalho = {k: v for k, v in dados.items() if k != "registros"}
    linhas = [json.dumps(r, ensure_ascii=False, separators=(",", ":")) for r in ordenados]
    texto = (json.dumps(cabecalho, ensure_ascii=False, separators=(",", ":"))[:-1]
             + ',"registros":[\n' + ",\n".join(linhas) + "\n]}\n")
    if caminho.exists() and caminho.read_text(encoding="utf-8") == texto:
        return False
    caminho.parent.mkdir(parents=True, exist_ok=True)
    tmp = caminho.with_suffix(".json.tmp")
    tmp.write_text(texto, encoding="utf-8")
    os.replace(tmp, caminho)
    return True


def arquivar(local: str, registros: list[dict], destino: Path = DESTINO,
             substituir: bool = True) -> dict:
    """Mescla ``registros`` no arquivo mensal de ``local``.

    ``substituir=False`` so acrescenta ids ainda ausentes (usado para
    recuperar versoes antigas sem sobrescrever conferencias mais novas).
    """
    por_mes: dict[str, list[dict]] = {}
    ignorados = 0
    for reg in registros:
        mes = mes_do_registro(reg)
        if mes is None:
            ignorados += 1
            continue
        por_mes.setdefault(mes, []).append(reg)

    resumo = {"local": local, "meses_alterados": [], "novos": 0,
              "atualizados": 0, "ignorados_sem_hora": ignorados}
    for mes, regs in sorted(por_mes.items()):
        caminho = destino / local / f"{mes}.json"
        atuais = carregar_mes(caminho)
        for reg in regs:
            antigo = atuais.get(reg["id"])
            if antigo is None:
                atuais[reg["id"]] = reg
                resumo["novos"] += 1
            elif substituir and antigo != reg:
                atuais[reg["id"]] = reg
                resumo["atualizados"] += 1
        if escrever_mes(caminho, local, mes, atuais):
            resumo["meses_alterados"].append(mes)
    escrever_indice(destino, local)
    return resumo


def escrever_indice(destino: Path, local: str) -> None:
    """Indice por local (cada robo so escreve na propria pasta: sem conflito de rebase)."""
    pasta = destino / local
    meses = {}
    for arq in sorted(pasta.glob("????-??.json")):
        with open(arq, "r", encoding="utf-8") as f:
            regs = json.load(f).get("registros", [])
        meses[arq.stem] = {
            "arquivo": arq.name,
            "total": len(regs),
            "conferidos": sum(1 for r in regs if r.get("status_auditoria") == "conferido"),
            "primeira_hora_modelo": min((r.get("hora_modelo") or "" for r in regs), default=None),
            "ultima_hora_modelo": max((r.get("hora_modelo") or "" for r in regs), default=None),
        }
    indice = {
        "schema_version": SCHEMA + "_indice",
        "local": local,
        "descricao": "Arquivo mensal permanente das previsoes ao vivo; gerado por scripts/arquivar_historico_ao_vivo.py.",
        "meses": meses,
    }
    texto = json.dumps(indice, ensure_ascii=False, indent=1) + "\n"
    caminho = pasta / "indice.json"
    if not caminho.exists() or caminho.read_text(encoding="utf-8") != texto:
        pasta.mkdir(parents=True, exist_ok=True)
        caminho.write_text(texto, encoding="utf-8")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--local", choices=sorted(FONTES), action="append")
    ap.add_argument("--entrada", type=Path, help="historico alternativo (exige um --local)")
    ap.add_argument("--destino", type=Path, default=DESTINO)
    ap.add_argument("--so-acrescentar", action="store_true",
                    help="nao substitui registros ja arquivados (recuperacao de versoes antigas)")
    args = ap.parse_args(argv)

    locais = args.local or sorted(FONTES)
    if args.entrada and len(locais) != 1:
        ap.error("--entrada exige exatamente um --local")

    falhou = False
    for local in locais:
        fonte = args.entrada or FONTES[local]
        if not fonte.exists():
            print(f"[arquivo] {local}: {fonte} ausente, nada a arquivar")
            continue
        try:
            regs = ler_registros(fonte)
        except (ValueError, json.JSONDecodeError) as exc:
            # Nunca apaga o arquivo por causa de um historico rolante invalido.
            print(f"[arquivo] {local}: historico invalido ({exc}); arquivo preservado")
            falhou = True
            continue
        resumo = arquivar(local, regs, args.destino, substituir=not args.so_acrescentar)
        print("[arquivo]", json.dumps(resumo, ensure_ascii=False))
    return 1 if falhou else 0


if __name__ == "__main__":
    sys.exit(main())
