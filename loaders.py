from collections.abc import Iterable
from pathlib import Path

import pandas as pd
import streamlit as st

from constants import (
    COLUNAS_BUSCA,
    LEITOS_ARQUIVOS,
    POPULACAO_ARQUIVOS,
)
from utils import (
    converter_numero,
    limpar_ibge,
    nome_coluna,
    texto_simples,
)


def localizar_arquivo(opcoes: Iterable[Path | str]) -> Path:
    for caminho in opcoes:
        arquivo = Path(caminho)

        if arquivo.exists():
            return arquivo

    candidatos = ", ".join(str(Path(caminho)) for caminho in opcoes)
    raise FileNotFoundError(f"Nenhum arquivo encontrado entre: {candidatos}")


def normalizar_colunas(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [nome_coluna(coluna) for coluna in df.columns]

    return df


def validar_colunas(df: pd.DataFrame, colunas: Iterable[str], origem: str) -> None:
    faltantes = [coluna for coluna in colunas if coluna not in df.columns]

    if faltantes:
        faltantes_txt = ", ".join(faltantes)
        raise KeyError(f"Colunas ausentes em {origem}: {faltantes_txt}")


def carregar_csv(caminho: Path, sep: str = ",") -> pd.DataFrame:
    try:
        return pd.read_csv(caminho, sep=sep, dtype=str, encoding="utf-8-sig")
    except UnicodeDecodeError:
        return pd.read_csv(caminho, sep=sep, dtype=str, encoding="latin1")


@st.cache_data(show_spinner=False)
def carregar_leitos() -> pd.DataFrame:
    arquivo = localizar_arquivo(LEITOS_ARQUIVOS)
    df = normalizar_colunas(carregar_csv(arquivo, sep=";"))

    validar_colunas(
        df,
        (
            "comp",
            "regiao",
            "uf",
            "co_ibge",
            "municipio",
            "cnes",
            "nome_estabelecimento",
            "leitos_existentes",
            "leitos_sus",
        ),
        str(arquivo),
    )

    return df


def carregar_populacao_ods(arquivo: Path) -> pd.DataFrame:
    planilha = pd.ExcelFile(arquivo, engine="odf")
    aba = next(
        (
            nome
            for nome in planilha.sheet_names
            if texto_simples(nome) == "MUNICIPIOS"
        ),
        planilha.sheet_names[0],
    )

    return pd.read_excel(
        planilha,
        sheet_name=aba,
        header=1,
        dtype=str,
    )


@st.cache_data(show_spinner=False)
def carregar_populacao() -> pd.DataFrame:
    arquivo = localizar_arquivo(POPULACAO_ARQUIVOS)

    if arquivo.suffix.lower() == ".ods":
        pop = carregar_populacao_ods(arquivo)
    else:
        pop = carregar_csv(arquivo)

    pop = normalizar_colunas(pop)

    if "co_ibge" not in pop.columns:
        validar_colunas(pop, ("cod_uf", "cod_munic"), str(arquivo))
        cod_uf = pop["cod_uf"].astype(str).str.extract(r"(\d+)")[0].str.zfill(2)
        cod_munic = (
            pop["cod_munic"]
            .astype(str)
            .str.extract(r"(\d+)")[0]
            .str.zfill(5)
            .str[:4]
        )
        pop["co_ibge"] = (
            cod_uf
            + cod_munic
        )

    if "populacao" not in pop.columns and "populacao_estimada" in pop.columns:
        pop["populacao"] = pop["populacao_estimada"]

    validar_colunas(pop, ("co_ibge", "populacao"), str(arquivo))

    pop["co_ibge"] = pop["co_ibge"].apply(limpar_ibge)
    pop["populacao"] = converter_numero(pop["populacao"])

    return (
        pop[["co_ibge", "populacao"]]
        .groupby("co_ibge", as_index=False)
        .agg(populacao=("populacao", "max"))
    )


def preparar_leitos(df: pd.DataFrame, pop: pd.DataFrame) -> pd.DataFrame:
    base = df.copy()

    base["comp"] = (
        base["comp"]
        .astype(str)
        .str.extract(r"(\d+)")[0]
        .fillna("")
        .str.strip()
    )

    competencia = base.loc[base["comp"].ne(""), "comp"].max()
    if not competencia:
        raise ValueError("Não foi possível identificar a competência dos leitos.")

    base = base[base["comp"] == competencia].copy()

    for coluna in ("leitos_existentes", "leitos_sus"):
        base[coluna] = converter_numero(base[coluna])

    for coluna in ("regiao", "uf", "municipio"):
        base[coluna] = (
            base[coluna]
            .fillna("")
            .astype(str)
            .str.upper()
            .str.strip()
        )

    for coluna in COLUNAS_BUSCA:
        if coluna not in base.columns:
            base[coluna] = ""

    base["co_ibge"] = base["co_ibge"].apply(limpar_ibge)

    base = base.merge(pop, on="co_ibge", how="left")
    base["populacao"] = (
        pd.to_numeric(base["populacao"], errors="coerce")
        .fillna(0)
    )

    base["existentes_nao_sus"] = (
        base["leitos_existentes"] - base["leitos_sus"]
    ).clip(lower=0)

    base["id_estabelecimento"] = (
        base["cnes"]
        .fillna("")
        .astype(str)
        .str.extract(r"(\d+)")[0]
        .fillna("")
        .str.zfill(7)
    )

    denominador = base["leitos_existentes"].where(base["leitos_existentes"] > 0)
    base["percentual_sus"] = (
        (base["leitos_sus"] / denominador) * 100
    ).fillna(0)

    base["texto_busca"] = (
        base[list(COLUNAS_BUSCA)]
        .fillna("")
        .astype(str)
        .agg(" ".join, axis=1)
    )

    return base.sort_values(["uf", "municipio", "nome_estabelecimento"])


def calcular_evolucao(df: pd.DataFrame) -> pd.DataFrame:
    evolucao = df.copy()

    evolucao["comp"] = (
        evolucao["comp"]
        .astype(str)
        .str.extract(r"(\d+)")[0]
        .fillna("")
    )

    for coluna in ("leitos_existentes", "leitos_sus"):
        evolucao[coluna] = converter_numero(evolucao[coluna])

    evolucao["co_ibge"] = evolucao["co_ibge"].apply(limpar_ibge)

    return evolucao.sort_values("comp")


@st.cache_data(show_spinner=False)
def carregar_base_app() -> tuple[pd.DataFrame, pd.DataFrame, str]:
    original = carregar_leitos()
    populacao = carregar_populacao()

    base = preparar_leitos(original, populacao)
    evolucao = calcular_evolucao(original)
    competencia = base["comp"].dropna().astype(str).max()

    return base, evolucao, competencia
