"""Continuação da linha percolação baixa só na família lrdcfvb (Clark variável), 24/11/2026: a ES ainda melhorava na g8.
4 gerações a mais (λ 48, μ 8, σ 0,07 → 0,05), mesma régua (chuva v4, J_pico, 17 janelas). Resultados em resultados_pb/.
Uso: python ciclo_pb2.py
"""
import ciclo_pb as c

c.FAM = "lrdcfvb"
for g, s in zip(range(9, 13), (0.07, 0.06, 0.06, 0.05)):
    c.rodada(f"pb-g{g}", ["es", "--resultados", str(c.RES), "--lam", "48", "--mu", "8", "--sigma", str(s),
                          "--semente", str(600 + g)])
print("concluído", flush=True)
