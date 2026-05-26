import unicodedata
from collections.abc import Iterable
from pathlib import Path

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql.functions import (
    col,
    concat_ws,
    countDistinct,
    lit,
    lpad,
    regexp_replace,
    sum as spark_sum,
    max as spark_max,
    trim,
    upper,
    when,
)

from constants import LEITOS_ARQUIVOS, POPULACAO_ARQUIVOS


def localizar_arquivo(opcoes: Iterable[Path | str]) -> Path:
    for caminho in opcoes:
        arquivo = Path(caminho)

        if arquivo.exists():
            return arquivo

    candidatos = ", ".join(str(Path(caminho)) for caminho in opcoes)
    raise FileNotFoundError(f"Nenhum arquivo encontrado entre: {candidatos}")


def nome_coluna_spark(valor: object) -> str:
    texto = unicodedata.normalize("NFKD", str(valor))
    texto = texto.encode("ascii", "ignore").decode("ascii")

    return (
        texto.strip()
        .lower()
        .replace(" ", "_")
        .replace(".", "")
        .replace("-", "_")
    )


def caminho_spark(arquivo: Path) -> str:
    return str(arquivo.resolve()).replace("\\", "/")


def normalizar_colunas(df: DataFrame) -> DataFrame:
    normalizado = df

    for coluna in df.columns:
        normalizado = normalizado.withColumnRenamed(coluna, nome_coluna_spark(coluna))

    return normalizado


def validar_colunas(df: DataFrame, colunas: Iterable[str], origem: str) -> None:
    faltantes = [coluna for coluna in colunas if coluna not in df.columns]

    if faltantes:
        faltantes_txt = ", ".join(faltantes)
        raise KeyError(f"Colunas ausentes em {origem}: {faltantes_txt}")


def coluna_numero(nome: str):
    texto = trim(col(nome).cast("string"))

    return (
        when(
            texto.contains(","),
            regexp_replace(regexp_replace(texto, "\\.", ""), ",", "."),
        )
        .when(texto.rlike(r"^-?\d+\.\d{1,2}$"), texto)
        .otherwise(regexp_replace(texto, "\\.", ""))
        .cast("double")
    )


def coluna_ibge(nome: str):
    digitos = regexp_replace(col(nome).cast("string"), "\\D", "")

    return lpad(digitos.substr(1, 6), 6, "0")


def criar_spark() -> SparkSession:
    return (
        SparkSession.builder
        .appName("PainelLeitosSUS")
        .getOrCreate()
    )


def ler_leitos(spark: SparkSession) -> DataFrame:
    arquivo = localizar_arquivo(LEITOS_ARQUIVOS)

    leitos = (
        spark.read
        .option("header", True)
        .option("sep", ";")
        .option("inferSchema", False)
        .option("encoding", "UTF-8")
        .csv(caminho_spark(arquivo))
    )

    leitos = normalizar_colunas(leitos)
    validar_colunas(
        leitos,
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

    return leitos


def ler_populacao(spark: SparkSession) -> DataFrame:
    candidatos_csv = [
        caminho
        for caminho in POPULACAO_ARQUIVOS
        if Path(caminho).suffix.lower() == ".csv"
    ]
    arquivo = localizar_arquivo(candidatos_csv)

    populacao = (
        spark.read
        .option("header", True)
        .option("inferSchema", False)
        .option("encoding", "UTF-8")
        .csv(caminho_spark(arquivo))
    )

    populacao = normalizar_colunas(populacao)
    validar_colunas(populacao, ("co_ibge", "populacao"), str(arquivo))

    return populacao


def preparar_leitos(leitos: DataFrame) -> DataFrame:
    leitos = (
        leitos
        .withColumn("comp", trim(col("comp").cast("string")))
        .withColumn("co_ibge", coluna_ibge("co_ibge"))
        .withColumn("leitos_existentes", coluna_numero("leitos_existentes"))
        .withColumn("leitos_sus", coluna_numero("leitos_sus"))
        .withColumn("municipio", upper(trim(col("municipio"))))
        .withColumn("uf", upper(trim(col("uf"))))
        .withColumn("regiao", upper(trim(col("regiao"))))
    )

    if "razao_social" not in leitos.columns:
        leitos = leitos.withColumn("razao_social", lit(""))

    return leitos.withColumn(
        "texto_busca",
        concat_ws(
            " ",
            col("nome_estabelecimento"),
            col("municipio"),
            col("cnes"),
            col("razao_social"),
        ),
    )


def preparar_populacao(populacao: DataFrame) -> DataFrame:
    return (
        populacao
        .withColumn("co_ibge", coluna_ibge("co_ibge"))
        .withColumn("populacao", coluna_numero("populacao"))
        .groupBy("co_ibge")
        .agg(spark_max("populacao").alias("populacao"))
    )


def filtrar_competencia_recente(leitos: DataFrame) -> tuple[DataFrame, str]:
    competencia = (
        leitos
        .select(spark_max("comp").alias("comp"))
        .collect()[0]["comp"]
    )

    return leitos.filter(col("comp") == competencia), competencia


def criar_base(leitos: DataFrame, populacao: DataFrame) -> DataFrame:
    base = leitos.join(
        populacao.select("co_ibge", "populacao"),
        on="co_ibge",
        how="left",
    )

    base = base.fillna({"populacao": 0})

    base = base.withColumn(
        "existentes_nao_sus",
        when(
            col("leitos_existentes") - col("leitos_sus") > 0,
            col("leitos_existentes") - col("leitos_sus"),
        ).otherwise(lit(0)),
    )

    return base.withColumn(
        "percentual_sus",
        when(
            col("leitos_existentes") > 0,
            (col("leitos_sus") / col("leitos_existentes")) * 100,
        ).otherwise(lit(0)),
    )


def exibir_resumos(base: DataFrame, leitos_historico: DataFrame, competencia: str) -> None:
    print(f"\n===== COMPETÊNCIA MAIS RECENTE: {competencia} =====")

    ufs_resumo = (
        base.groupBy("regiao", "uf")
        .agg(
            spark_sum("leitos_sus").alias("leitos_sus"),
            spark_sum("leitos_existentes").alias("leitos_existentes"),
            spark_sum("existentes_nao_sus").alias("existentes_nao_sus"),
            countDistinct("cnes").alias("estabelecimentos"),
        )
        .orderBy(col("leitos_sus").desc())
    )

    print("\n===== RESUMO POR UF =====")
    ufs_resumo.show(truncate=False)

    municipios = (
        base.groupBy("regiao", "uf", "municipio", "co_ibge")
        .agg(
            spark_sum("leitos_sus").alias("leitos_sus"),
            spark_sum("leitos_existentes").alias("leitos_existentes"),
            countDistinct("cnes").alias("estabelecimentos"),
            spark_max("populacao").alias("populacao"),
        )
        .withColumn(
            "sus_por_10mil",
            when(
                col("populacao") > 0,
                (col("leitos_sus") / col("populacao")) * 10000,
            ).otherwise(lit(0)),
        )
        .orderBy(col("sus_por_10mil").desc())
    )

    print("\n===== RESUMO POR MUNICÍPIO =====")
    municipios.show(truncate=False)

    evolucao = (
        leitos_historico.groupBy("comp")
        .agg(
            spark_sum("leitos_sus").alias("leitos_sus"),
            spark_sum("leitos_existentes").alias("leitos_existentes"),
        )
        .orderBy("comp")
    )

    print("\n===== EVOLUÇÃO =====")
    evolucao.show(truncate=False)

    simulacao = (
        base
        .withColumn("ocupacao_pct", when(col("leitos_sus") > 0, lit(84)).otherwise(lit(0)))
        .withColumn("ocupados", ((col("leitos_sus") * col("ocupacao_pct")) / 100).cast("int"))
        .withColumn("vagas_agora", (col("leitos_sus") - col("ocupados")).cast("int"))
        .withColumn(
            "fila_simulada",
            when(
                col("ocupacao_pct") >= 85,
                (col("leitos_sus") * 0.15).cast("int"),
            ).otherwise(lit(0)),
        )
        .withColumn(
            "status",
            when(col("leitos_sus") <= 0, lit("Sem SUS"))
            .when(col("ocupacao_pct") >= 90, lit("Crítico"))
            .when(col("ocupacao_pct") >= 80, lit("Atenção"))
            .otherwise(lit("Estável")),
        )
        .orderBy(col("leitos_sus").desc())
    )

    print("\n===== SIMULAÇÃO =====")
    simulacao.select(
        "nome_estabelecimento",
        "municipio",
        "uf",
        "leitos_sus",
        "ocupacao_pct",
        "fila_simulada",
        "status",
    ).show(truncate=False)


def main() -> None:
    spark = criar_spark()
    spark.sparkContext.setLogLevel("WARN")

    try:
        leitos_historico = preparar_leitos(ler_leitos(spark))
        populacao = preparar_populacao(ler_populacao(spark))
        leitos_recentes, competencia = filtrar_competencia_recente(leitos_historico)
        base = criar_base(leitos_recentes, populacao)

        exibir_resumos(base, leitos_historico, competencia)
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
