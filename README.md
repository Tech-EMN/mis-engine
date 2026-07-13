# MIS Engine — Backend Pipeline

Motor de extração e análise de projetos arquitetônicos para o MIS (MGroup Intelligence System).

**Status:** Draft C (Proof-of-Concept) — funcional, não production-ready.

## O que faz

Pipeline híbrido que processa arquivos de projeto (PDF, DXF, DWG) e extrai:
- Ambientes (rooms) com áreas, perímetros e dimensões
- Faces construtivas (piso, teto, paredes)
- Labels de ambientes (via TEXT/MTEXT no DXF ou Vision AI no PDF)
- Scoring de confiança para revisão humana

## Stack (100% OSS + AI API opcional)

| Formato | Engine | Biblioteca |
|---------|--------|-----------|
| PDF | Poppler → PNG → Claude/Gemini Vision | `pdftoppm`, `anthropic` |
| DXF | ezdxf → shapely | `ezdxf`, `shapely` |
| DWG | ⚠️ Requer conversão prévia DWG→DXF | ODA File Converter ou export AutoCAD |

## Estrutura

```
pipeline/          # Motor de extração
  mis_pipeline.py  # Pipeline principal (Draft C)
  extract_dwg.py   # Extrator DWG standalone
samples/           # Outputs de amostra
prompts/           # Templates de prompt Vision AI
docs/
  planning/        # Árvore de planejamento (L0→L3)
  lessons/         # Lições aprendidas
```

## Uso Rápido

```python
from pipeline.mis_pipeline import MISPipeline

pipeline = MISPipeline(secrets={
    'ANTHROPIC_API_KEY': 'sk-...'  # opcional, para PDFs
})

result = pipeline.process('projeto.dxf')
print(f'{len(result.rooms)} ambientes extraídos')

# Exportar
json_out = pipeline.to_json(result)
csv_out = pipeline.to_csv(result)
```

## Dependências

```bash
pip install ezdxf shapely anthropic
# Poppler (sistema): apt install poppler-utils
```

## Fragilidades Conhecidas

| ID | Descrição | Mitigação |
|----|-----------|-----------|
| F2 | DWG requer conversão DWG→DXF | Exportar como DXF do AutoCAD ou usar ODA File Converter |
| F11 | DXF sem TEXT/MTEXT → ambientes sem nome | Vision AI para nomear por contexto geométrico |

## Roadmap

- [ ] DWG→DXF conversion integrada (ODA CLI wrapper)
- [ ] Supabase integration para persistência
- [ ] API REST (FastAPI) para o front-end
- [ ] CI/CD pipeline
- [ ] Testes unitários e de integração

---

**Projeto MIS:** [mis-mis](https://github.com/Tech-EMN/mis-mis) (front-end)  
**Dashboard:** [mis-dashboard.netlify.app](https://mis-dashboard.netlify.app)  
**Landing:** [tech-emn.github.io/mis-mis](https://tech-emn.github.io/mis-mis)
