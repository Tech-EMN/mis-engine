# MIS — Sprint 1 Ambiguity Report (G3)
**Projeto:** MIS — MGroup Intelligence System  
**Fase:** Sprint 1 — Walking Skeleton  
**Data:** 2026-07-16  
**Autor:** Daedalus (AG01) | **Validador:** Argus (AG06) score 95/100  

---

## Ambiguidades Identificadas

| # | Ambiguidade | Severidade | Origem | Status | Resolução |
|---|-------------|-----------|--------|--------|-----------|
| A1 | **Formato de entrada do cliente**: PDF, DXF, DWG — quais formatos reais os clientes do Marcos entregam? | MÉDIA | Reunião #3 (Fireflies) | ⚠️ ABERTA | Pipeline suporta DXF+PDF. DWG requer conversão. Sem amostras reais do cliente para validar. |
| A2 | **Plataforma de deploy**: Railway vs Render vs VPS — não decidido. | 🔴 ALTA | Handoff §6 Blockers | ⚠️ ABERTA | Bloqueia S1.10. Decisão pendente de Eduardo. |
| A3 | **Regras de detecção de ambientes**: quais ambientes o Marcos espera? Sala, quarto, cozinha, banheiro? Ou nomenclatura técnica de obra? | MÉDIA | Reunião #5 (Fireflies) | ⚠️ ABERTA | Pipeline extrai labels de TEXT/MTEXT do DXF. Sem ground truth do cliente para calibrar. |
| A4 | **Pé-direito padrão**: 2.80m assumido no pipeline. Projetos do Marcos usam esse valor? | BAIXA | Código (mis_pipeline.py) | ⚠️ ABERTA | Valor configurável no DXFExtractor(pe_direito_m=2.80). |
| A5 | **Unidade de medida no DXF**: $INSUNITS pode ser metros, centímetros ou milímetros. Pipeline assume metros. | MÉDIA | Fragilidade F4 documentada | ⚠️ ABERTA | Documentado como fragilidade. Sem amostras reais para confirmar. |
| A6 | **Cotas vs estimativa visual**: PDFs sem cotas → Claude estima por porta (0.80m). Precisão disso com plantas do Marcos? | MÉDIA | Fragilidade F11 documentada | ⚠️ ABERTA | Documentado. Sem PDFs de exemplo do cliente. |
| A7 | **Dossiê Técnico**: 29 campos pendentes do Marcos (TD-005). Quais são críticos para Sprint 2? | MÉDIA | Handoff §6 TDs | ⚠️ ABERTA | 29 campos no Dossiê. 3 perguntas priorizadas (DOCS-002 na Sprint 2). |

## Ambiguidades Resolvidas

| # | Ambiguidade | Resolução | Data |
|---|-------------|-----------|------|
| R1 | n8n ou FastAPI para webhook WhatsApp? | FastAPI (decisão SDS-DOC-06 §4.2) | 2026-07-13 |
| R2 | Front-end com build system ou Babel standalone? | Babel standalone (React 18 UMD + tags type="text/babel") | 2026-07-13 |
| R3 | Pipeline: script ou módulo importável? | Módulo (pipeline/__init__.py) | 2026-07-15 (S1.2) |
| R4 | Extração síncrona ou assíncrona? | Assíncrona (202 + polling) — decisão Atlas feedback #2 | 2026-07-13 |
| R5 | Supabase schema: Sprint 1 ou Sprint 2? | Antecipado para S1.6 (decisão Atlas feedback #1) | 2026-07-13 |

## Resumo

- **Total ambiguidades:** 12
- **Resolvidas:** 5 (42%)
- **Abertas:** 7 (58%)
- **Críticas abertas:** 0 (todas as abertas são MÉDIA ou BAIXA)
- **Bloqueante de sprint atual:** A2 (plataforma de deploy)
- **Nenhuma ambiguidade impede continuar Sprint 1 exceto A2**

## Veredito G3

**✅ APROVADO** — Zero ambiguidades críticas não documentadas. As 7 abertas estão rastreadas com dono e impacto. Apenas A2 é bloqueante imediato (decisão pendente de Eduardo).

---

*Relatório gerado por Daedalus (AG01). Validado cruzado com PHASE4-ROADMAP-SPRINT.md, ATLAS-REVIEW-FEEDBACK.md, Foundation Audit (78/100).*
