from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data"
STYLE_FILE = ROOT_DIR / "styles.css"


LEITOS_ARQUIVOS = (
    DATA_DIR / "Leitos_2026.csv",
    DATA_DIR / "Leitos_2026 (1).csv",
    ROOT_DIR / "Leitos_2026.csv",
    ROOT_DIR / "Leitos_2026 (1).csv",
)

POPULACAO_ARQUIVOS = (
    DATA_DIR / "populacao_cache.csv",
    DATA_DIR / "POP2025_20260113.ods",
    ROOT_DIR / "populacao_cache.csv",
    ROOT_DIR / "POP2025_20260113.ods",
)


UF_CODIGOS = {
    "RO": "11",
    "AC": "12",
    "AM": "13",
    "RR": "14",
    "PA": "15",
    "AP": "16",
    "TO": "17",
    "MA": "21",
    "PI": "22",
    "CE": "23",
    "RN": "24",
    "PB": "25",
    "PE": "26",
    "AL": "27",
    "SE": "28",
    "BA": "29",
    "MG": "31",
    "ES": "32",
    "RJ": "33",
    "SP": "35",
    "PR": "41",
    "SC": "42",
    "RS": "43",
    "MS": "50",
    "MT": "51",
    "GO": "52",
    "DF": "53",
}


COLUNAS_BUSCA = (
    "nome_estabelecimento",
    "municipio",
    "cnes",
    "razao_social",
)

COLUNAS_RESUMO = (
    "uf",
    "municipio",
    "nome_estabelecimento",
    "leitos_existentes",
    "leitos_sus",
)


PRESSAO_CENARIOS = {
    "Normal": {
        "ocupacao_base": 0.64,
        "peso_fila": 0.16,
    },
    "Alta demanda": {
        "ocupacao_base": 0.76,
        "peso_fila": 0.28,
    },
    "Surto / emergência": {
        "ocupacao_base": 0.86,
        "peso_fila": 0.40,
    },
}

PESO_OCUPACAO = 0.55
PESO_FILA = 0.25
PESO_PRESSAO = 0.20

STATUS_CORES = {
    "Estável": "#22c55e",
    "Atenção": "#f59e0b",
    "Crítico": "#ef4444",
    "Sem SUS": "#64748b",
}
