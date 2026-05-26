import unicodedata

import pandas as pd


def _normalizar_numero_texto(valor: object) -> str:
    texto = str(valor).strip()

    if "," in texto:
        return texto.replace(".", "").replace(",", ".")

    if texto.count(".") == 1:
        parte_decimal = texto.rsplit(".", 1)[1]
        if 1 <= len(parte_decimal) <= 2:
            return texto

    return texto.replace(".", "")


def texto_simples(valor: object) -> str:
    """Normaliza texto para buscas sem acento e sem diferença de caixa."""
    texto = unicodedata.normalize("NFKD", str(valor))
    texto = texto.encode("ascii", "ignore").decode("ascii")

    return " ".join(texto.upper().split())


def nome_coluna(valor: object) -> str:
    texto = unicodedata.normalize("NFKD", str(valor))
    texto = texto.encode("ascii", "ignore").decode("ascii")

    return (
        texto.strip()
        .lower()
        .replace(" ", "_")
        .replace(".", "")
        .replace("-", "_")
    )


def converter_numero(serie: pd.Series) -> pd.Series:
    return (
        pd.to_numeric(
            serie.apply(_normalizar_numero_texto),
            errors="coerce",
        )
        .fillna(0)
    )


def formatar_numero(valor: float) -> str:
    if pd.isna(valor):
        return "0"

    return f"{int(round(float(valor))):,}".replace(",", ".")


def formatar_decimal(valor: float, casas: int = 2) -> str:
    if pd.isna(valor):
        return "0,00"

    return (
        f"{float(valor):,.{casas}f}"
        .replace(",", "X")
        .replace(".", ",")
        .replace("X", ".")
    )


def limpar_ibge(valor: object) -> str:
    codigo = "".join(ch for ch in str(valor) if ch.isdigit())

    return codigo[:6].zfill(6)


def primeiro_valor(serie: pd.Series) -> str:
    valores = serie.dropna().astype(str).str.strip()
    valores = valores[valores != ""]

    return "" if valores.empty else valores.iloc[0]
