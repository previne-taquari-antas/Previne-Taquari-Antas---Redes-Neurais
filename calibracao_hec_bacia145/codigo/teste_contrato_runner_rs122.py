import copy
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from contrato_rs122 import conferir_fontes, conferir_horas, conferir_metadata, conferir_extensao
from congelar_fontes_rs122 import fingerprint


class RunnerContratoTest(unittest.TestCase):
    def test_extension_separate_and_pinned(self):
        actual = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "experimentos/rs122"
            folder.mkdir(parents=True)
            for name in ("contrato.json", "fontes.json", "extensao_2min.json"):
                (folder / name).write_bytes((actual / "experimentos/rs122" / name).read_bytes())
            cfg = json.loads((folder / "contrato.json").read_text(encoding="utf-8"))
            valid = conferir_extensao(root, cfg, 2)
            for dt in (1, 5, 10):
                with self.assertRaises(ValueError):
                    conferir_extensao(root, cfg, dt)
            for field, value in (("passo_novo_min", 1), ("exigir_ausencia_tc_floor_42403", False),
                                 ("snapshot_fontes_sha256_lf", "0"*64)):
                changed = copy.deepcopy(valid)
                changed[field] = value
                (folder / "extensao_2min.json").write_text(json.dumps(changed), encoding="utf-8")
                with self.assertRaises(ValueError):
                    conferir_extensao(root, cfg, 2)
            (folder / "extensao_2min.json").write_text(json.dumps(valid), encoding="utf-8")
            (folder / "contrato.json").write_text(json.dumps(dict(cfg, passos_min=[2, 1])), encoding="utf-8")
            with self.assertRaises(ValueError):
                conferir_extensao(root, cfg, 2)

    def test_hours(self):
        ini, fim = datetime(2023, 7, 4, 18), datetime(2023, 7, 4, 20)
        valid = [f"2023-07-04T{h}:00:00" for h in (18, 19, 20)]
        conferir_horas(valid, ini, fim)
        for bad in (valid[::2], [valid[0], valid[0], valid[2]], [valid[0], valid[2], valid[1]],
                    [f"2023-07-04T{h}:00:00" for h in (19, 20, 21)]):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                conferir_horas(bad, ini, fim)

    def test_frozen_content_not_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "experimentos/rs122").mkdir(parents=True)
            p = root / "pedido.json"
            pedido = {"id": "dl-piloto-c000", "p": {"k1": 28}, "papeis": {"E18": "validacao"}}
            p.write_text(json.dumps(pedido))
            geo = {"manifesto_sha256": "a" * 64, "particao_sha256": "b" * 64}
            cfg = {"geometria": geo, "janelas": ["S2023_07", "S2023_11"], "passos_min": [10, 5, 1], "bracos": ["A", "B0", "B1"]}
            snap = {"geometria_conferida_localmente": geo, "entradas": {"pedido.json": fingerprint(p)}}
            (root / "experimentos/rs122/fontes.json").write_text(json.dumps(snap))
            conferir_fontes(root, cfg)
            for change in ("p", "papeis"):
                bad = copy.deepcopy(pedido)
                bad[change] = {"k1": 29} if change == "p" else {"E18": "calibracao"}
                p.write_text(json.dumps(bad))
                with self.assertRaisesRegex(ValueError, "Fonte difere"):
                    conferir_fontes(root, cfg)
            p.write_text(json.dumps(pedido))
            cfg["bracos"] = ["A", "B0", "B0"]
            with self.assertRaisesRegex(ValueError, "Desenho"):
                conferir_fontes(root, cfg)

    def test_dss_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "meta.json"
            good = {"node": "J", "pathname": "//J/FLOW/a/10Minute/RUN/", "units": "M3/S", "type": "INST-VAL", "interval": 10, "count": 3}
            p.write_text(json.dumps([good]))
            conferir_metadata(p, ["J"], 10, 3)
            for field, value in (("units", "MM"), ("type", "PER-CUM"), ("interval", 5), ("count", 2), ("pathname", "//J/PRECIP/a/b/c/")):
                p.write_text(json.dumps([{**good, field: value}]))
                with self.subTest(field=field), self.assertRaises(ValueError):
                    conferir_metadata(p, ["J"], 10, 3)


if __name__ == "__main__":
    unittest.main()
