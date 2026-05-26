import hashlib

import numpy as np
import pandas as pd

from constants import (
    COLUNAS_BUSCA,
    PESO_FILA,
    PESO_OCUPACAO,
    PESO_PRESSAO,
    PRESSAO_CENARIOS,
)
from utils import texto_simples


def pesquisar_hospital(df: pd.DataFrame, busca: str) -> pd.DataFrame:
    if not busca:
        return df

    colunas = [coluna for coluna in COLUNAS_BUSCA if coluna in df.columns]
    if not colunas:
        return df.iloc[0:0]

    texto = (
        df[colunas]
        .fillna("")
        .astype(str)
        .agg(" ".join, axis=1)
        .apply(texto_simples)
    )

    termos = texto_simples(busca).split()
    mascara = pd.Series(True, index=df.index)

    for termo in termos:
        mascara &= texto.str.contains(termo, regex=False, na=False)

    return df[mascara]


def perfil_operacional(valor: object) -> float:
    """Gera uma variação fixa por hospital, sem mudar a cada recarga."""
    texto = str(valor).encode("utf-8", errors="ignore")
    digest = hashlib.sha1(texto).hexdigest()
    bruto = int(digest[:8], 16) / 0xFFFFFFFF

    return bruto


def calcular_ocupacao(df: pd.DataFrame, cenario: str = "Alta demanda") -> pd.DataFrame:
    if df.empty:
        return df.copy()

    sim = df.copy()
    parametros = PRESSAO_CENARIOS.get(cenario, PRESSAO_CENARIOS["Alta demanda"])

    capacidade = sim["leitos_sus"].clip(lower=0)
    leitos_municipio = (
        sim.groupby("co_ibge")["leitos_sus"]
        .transform("sum")
        .clip(lower=0)
    )

    taxa_municipal = np.where(
        sim["populacao"] > 0,
        leitos_municipio / sim["populacao"] * 10000,
        0,
    )

    pressao_territorial = np.clip((10 - taxa_municipal) / 10, -0.08, 0.14)
    ajuste_porte = np.select(
        [
            (capacidade > 0) & (capacidade < 20),
            capacidade >= 120,
        ],
        [
            0.04,
            -0.03,
        ],
        default=0,
    )

    identificador = sim["id_estabelecimento"].where(
        sim["id_estabelecimento"].astype(str).str.strip().ne(""),
        sim["nome_estabelecimento"],
    )
    variacao_hospital = identificador.apply(perfil_operacional) * 0.28 - 0.15

    ocupacao = np.where(
        capacidade > 0,
        np.clip(
            parametros["ocupacao_base"]
            + pressao_territorial
            + ajuste_porte
            + variacao_hospital,
            0.35,
            0.99,
        ),
        0,
    )

    sim["ocupacao_pct"] = ocupacao * 100
    sim["ocupados"] = np.round(capacidade * ocupacao).astype(int)
    sim["vagas_agora"] = (capacidade - sim["ocupados"]).clip(lower=0).astype(int)

    sim["altas_previstas"] = np.round(sim["ocupados"] * 0.05).astype(int)
    sim["altas_pendentes"] = np.round(
        sim["altas_previstas"] * np.clip(0.18 + pressao_territorial, 0.08, 0.38)
    ).astype(int)

    sim["vagas_6h"] = (
        sim["vagas_agora"]
        + sim["altas_previstas"]
        - sim["altas_pendentes"]
    ).clip(lower=0).astype(int)

    sim["fila"] = np.round(
        np.maximum(
            0,
            ((ocupacao - 0.78) * capacidade)
            + (np.maximum(pressao_territorial, 0) * capacidade * parametros["peso_fila"]),
        )
    ).astype(int)

    capacidade_segura = capacidade.replace(0, 1)
    sim["indice_pressao"] = (
        sim["ocupacao_pct"] * PESO_OCUPACAO
        + np.clip(sim["fila"] / capacidade_segura * 100, 0, 100) * PESO_FILA
        + np.maximum(pressao_territorial, 0) * 100 * PESO_PRESSAO
    ).clip(0, 100)

    return sim


def gerar_status_leitos(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df.copy()

    sim = df.copy()

    sim["status"] = np.select(
        [
            (sim["leitos_sus"] <= 0) & (sim["existentes_nao_sus"] > 0),
            (sim["ocupacao_pct"] >= 92) | (sim["indice_pressao"] >= 78),
            (sim["ocupacao_pct"] >= 78) | (sim["indice_pressao"] >= 58),
        ],
        [
            "Sem SUS",
            "Crítico",
            "Atenção",
        ],
        default="Estável",
    )

    sim["acao"] = np.select(
        [
            sim["status"].eq("Sem SUS"),
            sim["status"].eq("Crítico") & (sim["vagas_6h"] <= 0),
            sim["status"].eq("Crítico") & (sim["fila"] > 0),
            sim["status"].eq("Atenção") & (sim["altas_pendentes"] > 0),
            sim["status"].eq("Atenção") & (sim["vagas_6h"] <= sim["fila"]),
            sim["status"].eq("Estável") & (sim["vagas_6h"] > sim["fila"]),
        ],
        [
            "Conferir pactuação SUS e possibilidade de contrato.",
            "Priorizar regulação, altas e transferência segura.",
            "Avaliar reforço de equipe e redistribuição de pacientes.",
            "Acelerar altas hospitalares previstas.",
            "Monitorar ocupação nas próximas 6h.",
            "Pode receber pacientes dentro da capacidade atual.",
        ],
        default="Monitoramento contínuo.",
    )

    ordem_status = {
        "Crítico": 0,
        "Atenção": 1,
        "Sem SUS": 2,
        "Estável": 3,
    }
    sim["ordem_status"] = sim["status"].map(ordem_status).fillna(9)

    return sim.sort_values(
        ["ordem_status", "indice_pressao", "fila", "vagas_6h"],
        ascending=[True, False, False, True],
    )
