import unittest
import numpy as np

from preparar_controle_rs122 import montante_restrita, caminho, incluir_conexao_final


class ControleTest(unittest.TestCase):
    def test_d8_whitebox(self):
        # Todos os oito vizinhos drenam para o centro; inclui a célula semente.
        p = np.array([[4, 8, 16], [2, 0, 32], [1, 128, 64]])
        self.assertEqual(int(montante_restrita(p, np.ones((3, 3), bool), (1, 1)).sum()), 9)

    def test_nao_atravessa_outra_subbacia(self):
        p = np.array([[2, 2, 0]])
        m = np.array([[True, False, True]])
        self.assertEqual(int(montante_restrita(p, m, (0, 2)).sum()), 1)

    def test_seed_externo(self):
        with self.assertRaisesRegex(ValueError, "fora"):
            montante_restrita(np.zeros((1, 1)), np.zeros((1, 1), bool), (0, 0))

    def test_particao_disjunta(self):
        p = np.array([[2, 2, 2, 0]])
        m = np.ones((1, 4), bool)
        up = montante_restrita(p, m, (0, 1))
        down = m & ~up
        self.assertEqual(up.tolist(), [[True, True, False, False]])
        self.assertTrue(np.array_equal(up | down, m))
        self.assertFalse(np.any(up & down))

    def test_caminho(self):
        p, links, acc = np.array([[2, 2, 2, 0]]), np.array([[211, 211, 211, 0]]), np.array([[2, 3, 4, 5]])
        self.assertEqual(caminho(p, links, acc, 211), [(0, 0), (0, 1), (0, 2)])

    def test_desconexo(self):
        with self.assertRaisesRegex(ValueError, "descontínuo"):
            caminho(np.array([[2, 2, 2, 0]]), np.array([[211, 0, 211, 0]]), np.array([[2, 3, 4, 5]]), 211)

    def test_ciclo(self):
        with self.assertRaisesRegex(ValueError, "Ciclo"):
            caminho(np.array([[2, 32]]), np.array([[211, 211]]), np.array([[2, 3]]), 211)

    def test_conexao_final(self):
        p, links = np.array([[2, 2, 2, 0]]), np.array([[211, 211, 211, 205]])
        path = [(0, 0), (0, 1), (0, 2)]
        self.assertEqual(incluir_conexao_final(path, p, links, 205), path + [(0, 3)])
        self.assertEqual(len(path), 3)
        with self.assertRaisesRegex(ValueError, "jusante"):
            incluir_conexao_final(path, p, links, 999)


if __name__ == "__main__":
    unittest.main()
