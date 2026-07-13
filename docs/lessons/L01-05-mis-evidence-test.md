# Lições Aprendidas — MIS Evidence Test

**Sessão:** 28-29/Jun/2026 | **Agente:** Daedalus (AG01)  
**Handoff:** HANDOFF-20260629.md

## L1 — Vision LLM lê cotas, não geometria
**What:** IA deu 100% de precisão porque LEU os números das cotas nos PDFs. Se não houver cotas, a precisão é imprevisível.
**Why it matters:** O pipeline DXF (determinístico) não tem essa fragilidade. Sempre prefira código sobre IA para matemática.

## L2 — DWG é o calcanhar do OSS
**What:** Após 1.5h tentando compilar LibreDWG, o veredito é claro: não existe leitor DWG OSS maduro.
**Why it matters:** A solução pragmática é o cliente exportar DXF (1 clique, R$0). Não vale a pena lutar com DWG binário.

## L3 — Geometria é matemática, nomes são semântica
**What:** ezdxf+shapely calculam áreas com precisão de engenharia (5ms). Mas nomear ambientes depende de TEXT no DXF ou de AI.
**Why it matters:** Separar geometria (determinística) de semântica (probabilística) é o design certo para sistemas de orçamento.

## L4 — Tenet converge rápido com pesquisa prévia
**What:** 3 subagentes produziram planos convergentes porque as 20+ fontes já haviam mapeado o espaço.
**Why it matters:** Investir em pesquisa antes do planejamento adversarial reduz o custo da síntese.

## L5 — 5ms vs 8.7s: determinístico > IA para geometria
**What:** DXF pipeline extrai 4 ambientes em 5ms a R$0. PDF pipeline leva 8.7s a R$0.01 e pode alucinar.
**Why it matters:** Para geometria pura, código determinístico é superior em velocidade, custo e precisão.
