"""Regression checks against archived training rows, not the robot's audit flag."""
import datetime as dt
import importlib.util
import unittest
from pathlib import Path

import numpy as np
import openpyxl
from previne.robo import gerar_previsao_ao_vivo as stz

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'mucum_training_contract', ROOT / 'codigo_python/01_previsao_ao_vivo/gerar_previsao_ao_vivo_mucum.py')
mucum = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mucum)


class TrainingContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.models = mucum.carregar_modelos()

    def test_stz_a20_including_4h_cascade_uses_trained_offsets(self):
        book = openpyxl.load_workbook(ROOT / stz.MODELO_2H_B_WORKBOOK, read_only=True, data_only=True)
        levels = {}
        for r in book['DADOS_FORM'].iter_rows(min_row=2, values_only=True):
            try:
                t = dt.datetime(*map(int, r[:5]))
            except (TypeError, ValueError):
                continue
            levels[t] = (r[32], r[33])
        book.close()
        active = openpyxl.load_workbook(ROOT / stz.MODELO_WORKBOOK, read_only=True, data_only=True)
        archived_inputs = []
        checked = 0
        for r in active['VAR'].iter_rows(min_row=2, values_only=True):
            archived_inputs.append(tuple(r[7:22]))
            t = dt.datetime(*map(int, r[:5]))
            vals = [levels.get(t-dt.timedelta(hours=h), (None, None))[1] for h in (0, 1, 19, 20)]
            if None in vals:
                continue
            series = {'86472000': {t-dt.timedelta(hours=h): v for h, v in zip((0,1,19,20), vals)}}
            self.assertEqual(stz._A_exato(series, '86472000', t, 20), r[21])
            self.assertEqual(stz._valor_nivel_exato(series, ('acel', '86472000', 20), t), r[21])
            checked += 1
        active.close()
        self.assertEqual(checked, 2677)
        for mat_path in (stz.MODELO_MAT, stz.MODELO_2H_B_MAT):
            mat = mucum.carregar_mat(ROOT / mat_path)
            inputs = np.asarray(mat["Ptot"], float)
            if inputs.shape[0] == 15:
                inputs = inputs.T
            np.testing.assert_allclose(inputs, archived_inputs, rtol=0, atol=1e-8)

    def test_mucum_4h_8h_reproduce_workbook_and_mat_inputs(self):
        for cfg in self.models:
            if cfg['modelo'] not in mucum.MODELOS_SEGUNDA_DIFERENCA:
                continue
            with self.subTest(model=cfg['modelo']):
                w = openpyxl.load_workbook(ROOT / cfg['arquivo_excel'], read_only=True, data_only=True)
                rows = list(w.worksheets[0].values)[1:]
                w.close()
                columns = {i['ordem']-1: 7+i['ordem']-1 for i in cfg['inputs']}
                level_cols = {str(i['estacao']): columns[i['ordem']-1] for i in cfg['inputs'] if i['tipo']=='nivel'}
                # Never bridge missing times or different historical flood events.
                events = {}
                for r in rows:
                    t = dt.datetime(*map(int, r[:4]))
                    event = events.setdefault(r[6], {})
                    for code, col in level_cols.items():
                        event.setdefault(code, {})[t] = r[col]
                checked = 0
                for r in rows:
                    t = dt.datetime(*map(int, r[:4]))
                    values = mucum.montar_inputs(cfg, events[r[6]], t)
                    for inp, actual in zip(cfg['inputs'], values):
                        if inp['tipo'].startswith('chuva') or actual is None:
                            continue
                        self.assertAlmostEqual(actual, r[7+inp['ordem']-1], places=7,
                                               msg=f"{cfg['modelo']} {t} {inp['nome']}")
                        checked += 1
                self.assertGreater(checked, 10000)
                mat = mucum.carregar_mat(cfg['mat'])
                trained = np.asarray(mat['Ptot'], float)
                if trained.shape[0] == cfg['n_inputs']:
                    trained = trained.T
                archived = {tuple(round(float(x), 7) for x in r[7:7+cfg['n_inputs']]) for r in rows}
                self.assertTrue(all(tuple(np.round(r, 7)) in archived for r in trained))

    def test_missing_second_lag_cannot_be_interpolated_or_replaced(self):
        cfg = next(c for c in self.models if c['horizonte']=='4h')
        t = dt.datetime(2026,11,12,16)
        series = {c: {t-dt.timedelta(hours=h): float(h*h+200) for h in range(41)} for c in cfg['estacoes']}
        del series['86472000'][t-dt.timedelta(hours=40)]
        self.assertIsNone(mucum.montar_inputs(cfg, series, t)[14])

    def test_2h_mucum_retains_its_own_hourly_formula(self):
        cfg = self.models[0]
        t = dt.datetime(2026,11,12,16)
        series = {c:{t-dt.timedelta(hours=h): float(h*h+200) for h in range(41)} for c in cfg['estacoes']}
        # A2: (200-201)-(204-209)=4, whereas step-2 curvature is 8.
        self.assertEqual(mucum.montar_inputs(cfg, series, t)[4], 4)

    def test_formula_change_does_not_reuse_old_error_metrics(self):
        model = next(c['modelo'] for c in self.models if c['horizonte']=='4h')
        old = {'horizonte':'4h','modelo':model,'status_auditoria':'conferido',
               'hora_alvo':mucum.agora_brt().isoformat(),'erro_abs_cm':124}
        self.assertIsNone(mucum.resumo_auditoria([old], '4h')['mae_24h_cm'])
        new = dict(old, formula_contract_version=mucum.FORMULA_SEGUNDA_DIFERENCA, erro_abs_cm=7)
        self.assertEqual(mucum.resumo_auditoria([old,new], '4h')['mae_24h_cm'], 7)
        self.assertIsNone(stz.resumo_auditoria([dict(old,horizonte='2h',modelo=stz.COMBO)], '2h', stz.COMBO)['mae_24h_cm'])

    def test_formula_migration_does_not_silently_unlock_blocked_model(self):
        model = next(c['modelo'] for c in self.models if c['horizonte']=='4h')
        out = {'modelo':model, 'status':'ok', 'nivel_previsto_cm':123, 'passos':[], 'disponivel':True}
        mucum.aplicar_guardrail_qualidade_horizontes({'4h':out}, [])
        self.assertFalse(out['disponivel'])
        self.assertEqual(out['bloqueio_publicacao'], 'revalidacao_formula_corrigida')
        self.assertEqual(out['previsao_reprovada_qualidade_cm'], 123)



if __name__ == '__main__':
    unittest.main()
