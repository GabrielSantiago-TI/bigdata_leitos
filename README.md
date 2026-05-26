Painel de Leitos SUS

Painel interativo em Streamlit para analise da distribuicao de leitos hospitalares do SUS no Brasil, com indicadores territoriais, filtros dinamicos, visualizacoes em Plotly e simulacao academica de ocupacao hospitalar.

Recursos principais

- Indicadores de estabelecimentos, municipios, populacao, leitos SUS e taxa por 10 mil habitantes.
- Filtros por hospital, municipio, UF e regiao.
- Graficos interativos para distribuicao territorial, ranking e evolucao.
- Simulacao de ocupacao, fila, vagas em 6 horas e status operacional.
- Pipeline opcional em PySpark para geracao de bases analiticas.

Arquivos principais

- `app.py`: aplicacao Streamlit.
- `charts.py`: graficos do painel.
- `constants.py`: constantes globais.
- `loaders.py`: leitura e preparacao dos dados.
- `simulation.py`: regras da simulacao.
- `spark_etl.py`: processamento analitico em PySpark.
- `styles.css`: identidade visual.
- `utils.py`: funcoes auxiliares.

Dados

- `data/Leitos_2026 (1).csv`
- `data/POP2025_20260113.ods`
- `data/base_app_cache.csv`
- `data/evolucao_cache.csv`
- `data/populacao_cache.csv`

Licenca

MIT
