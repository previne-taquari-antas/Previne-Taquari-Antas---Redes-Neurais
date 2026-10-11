import tempfile
import unittest
from pathlib import Path

from auditar_origem_rs122 import verificar


class OrigemTest(unittest.TestCase):
    def files(self, row, data):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        x, c = Path(tmp.name) / "raw.xml", Path(tmp.name) / "obs.csv"
        x.write_text("<root>" + row + "</root>", encoding="utf-8")
        c.write_text("data_hora,nivel_cm,vazao_m3s,chuva_mm\n" + data, encoding="utf-8")
        return x, c

    def row(self, q="9", cod="86298000"):
        return f"<DadosHidrometereologicos><CodEstacao>{cod}</CodEstacao><DataHora>2023-01-01 00:00:00 </DataHora><Nivel>100</Nivel><Vazao>{q}</Vazao></DadosHidrometereologicos>"

    def test_equal(self):
        self.assertEqual(verificar(*self.files(self.row(), "2023-01-01 00:00:00,100,9,\n"))["status"], "transcricao_confirmada")

    def test_conflicting_duplicate_xml(self):
        r = verificar(*self.files(self.row("8") + self.row(), "2023-01-01 00:00:00,100,9,\n"))
        self.assertEqual(r["status"], "falha")
        self.assertEqual(len(r["conflitos_xml"]), 1)

    def test_wrong_station(self):
        self.assertEqual(verificar(*self.files(self.row(cod="999"), "2023-01-01 00:00:00,100,9,\n"))["status"], "falha")

    def test_wrong_value(self):
        self.assertEqual(verificar(*self.files(self.row(), "2023-01-01 00:00:00,100,8,\n"))["status"], "falha")

    def test_empty(self):
        self.assertEqual(verificar(*self.files("", ""))["status"], "falha")


if __name__ == "__main__":
    unittest.main()
