from html import escape

import pandas as pd
import streamlit as st

from charts import (
    grafico_barras,
    grafico_densidade,
    grafico_evolucao,
    grafico_setores,
)
from constants import (
    COLUNAS_RESUMO,
    PRESSAO_CENARIOS,
    STATUS_CORES,
    STYLE_FILE,
)
from loaders import carregar_base_app
from simulation import (
    calcular_ocupacao,
    gerar_status_leitos,
    pesquisar_hospital,
)
from utils import formatar_decimal, formatar_numero


def configurar_pagina() -> None:
    st.set_page_config(
        page_title="Painel de Leitos SUS",
        page_icon="🏥",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    if STYLE_FILE.exists():
        st.markdown(
            f"<style>{STYLE_FILE.read_text(encoding='utf-8')}</style>",
            unsafe_allow_html=True,
        )


def aplicar_filtros(df):
    st.sidebar.title("Filtros")

    busca = st.sidebar.text_input("Buscar hospital ou município")
    filtrado = pesquisar_hospital(df, busca)

    regioes = sorted(filtrado["regiao"].dropna().unique())
    regioes_sel = st.sidebar.multiselect("Região", regioes, default=regioes)
    filtrado = filtrado[filtrado["regiao"].isin(regioes_sel)]

    ufs = sorted(filtrado["uf"].dropna().unique())
    ufs_sel = st.sidebar.multiselect("UF", ufs, default=ufs)
    filtrado = filtrado[filtrado["uf"].isin(ufs_sel)]

    municipios = sorted(filtrado["municipio"].dropna().unique())
    municipios_sel = st.sidebar.multiselect("Município", municipios)

    if municipios_sel:
        filtrado = filtrado[filtrado["municipio"].isin(municipios_sel)]

    return filtrado


def calcular_populacao_contexto(df) -> float:
    if df.empty:
        return 0

    return (
        df.groupby("co_ibge")["populacao"]
        .max()
        .sum()
    )


def calcular_kpis(df) -> dict[str, float]:
    total_populacao = calcular_populacao_contexto(df)
    total_sus = df["leitos_sus"].sum()

    return {
        "estabelecimentos": df["id_estabelecimento"].nunique(),
        "municipios": df["co_ibge"].nunique(),
        "populacao": total_populacao,
        "leitos_existentes": df["leitos_existentes"].sum(),
        "leitos_sus": total_sus,
        "taxa_sus": total_sus / total_populacao * 10000 if total_populacao > 0 else 0,
    }


def renderizar_cabecalho(competencia: str) -> None:
    st.title("Painel de Leitos SUS")
    st.caption(f"Competência utilizada: {competencia}")


def renderizar_metricas(kpis: dict[str, float]) -> None:
    colunas = st.columns(5)

    colunas[0].metric("Estabelecimentos", formatar_numero(kpis["estabelecimentos"]))
    colunas[1].metric("Municípios", formatar_numero(kpis["municipios"]))
    colunas[2].metric("População", formatar_numero(kpis["populacao"]))
    colunas[3].metric("Leitos SUS", formatar_numero(kpis["leitos_sus"]))
    colunas[4].metric("SUS / 10 mil", formatar_decimal(kpis["taxa_sus"]))


def renderizar_resumo(df, kpis: dict[str, float]) -> None:
    st.subheader("Resumo geral")

    percentual = (
        kpis["leitos_sus"] / kpis["leitos_existentes"] * 100
        if kpis["leitos_existentes"] > 0
        else 0
    )

    colunas = st.columns(3)
    colunas[0].metric("Leitos existentes", formatar_numero(kpis["leitos_existentes"]))
    colunas[1].metric("Leitos SUS", formatar_numero(kpis["leitos_sus"]))
    colunas[2].metric("% SUS", f"{formatar_decimal(percentual)}%")

    if df.empty:
        st.warning("Nenhum registro encontrado para os filtros selecionados.")
        return

    st.dataframe(
        df[list(COLUNAS_RESUMO)],
        use_container_width=True,
        hide_index=True,
    )


def renderizar_graficos(df, evolucao_base) -> None:
    st.subheader("Análises gráficas")

    if df.empty:
        exemplo_densidade = "sem dados no filtro atual."
        exemplo_barras = "sem dados no filtro atual."
        exemplo_setores = "sem dados no filtro atual."
    else:
        municipios_regionais = (
            df.groupby(["regiao", "co_ibge"], as_index=False)
            .agg(
                populacao=("populacao", "max"),
                leitos_sus=("leitos_sus", "sum"),
            )
        )
        resumo_regional = (
            municipios_regionais.groupby("regiao", as_index=False)
            .agg(
                populacao=("populacao", "sum"),
                leitos_sus=("leitos_sus", "sum"),
                municipios=("co_ibge", "count"),
            )
        )
        resumo_regional["sus_por_10mil"] = 0.0
        com_populacao = resumo_regional["populacao"] > 0
        resumo_regional.loc[com_populacao, "sus_por_10mil"] = (
            resumo_regional.loc[com_populacao, "leitos_sus"]
            / resumo_regional.loc[com_populacao, "populacao"]
            * 10000
        )
        regiao_densidade = resumo_regional.sort_values("sus_por_10mil", ascending=False).iloc[0]
        exemplo_densidade = (
            f"na região {regiao_densidade['regiao']}, o recorte possui "
            f"{formatar_numero(regiao_densidade['municipios'])} municípios e "
            f"{formatar_decimal(regiao_densidade['sus_por_10mil'])} leitos SUS por 10 mil habitantes."
        )

        uf_resumo = (
            df.groupby("uf", as_index=False)
            .agg(
                leitos_sus=("leitos_sus", "sum"),
                existentes_nao_sus=("existentes_nao_sus", "sum"),
            )
            .sort_values("leitos_sus", ascending=False)
            .iloc[0]
        )
        exemplo_barras = (
            f"{uf_resumo['uf']} aparece com {formatar_numero(uf_resumo['leitos_sus'])} "
            f"leitos SUS e {formatar_numero(uf_resumo['existentes_nao_sus'])} leitos não SUS."
        )

        regiao_resumo = (
            df.groupby("regiao", as_index=False)
            .agg(leitos_sus=("leitos_sus", "sum"))
            .sort_values("leitos_sus", ascending=False)
            .iloc[0]
        )
        exemplo_setores = (
            f"a região {regiao_resumo['regiao']} concentra "
            f"{formatar_numero(regiao_resumo['leitos_sus'])} leitos SUS no filtro atual."
        )

    evolucao_resumo = (
        evolucao_base.groupby(["comp", "regiao"], as_index=False)
        .agg(leitos_sus=("leitos_sus", "sum"))
        .sort_values(["regiao", "comp"])
    )
    if not evolucao_resumo.empty and evolucao_resumo["comp"].nunique() >= 2:
        variacoes = []
        for regiao, grupo in evolucao_resumo.groupby("regiao"):
            grupo = grupo.sort_values("comp")
            variacoes.append(
                {
                    "regiao": regiao,
                    "primeira_comp": grupo.iloc[0]["comp"],
                    "ultima_comp": grupo.iloc[-1]["comp"],
                    "variacao": grupo.iloc[-1]["leitos_sus"] - grupo.iloc[0]["leitos_sus"],
                }
            )
        variacoes_df = pd.DataFrame(variacoes)
        destaque = variacoes_df.iloc[variacoes_df["variacao"].abs().idxmax()]
        direcao = "aumentou" if destaque["variacao"] >= 0 else "reduziu"
        exemplo_evolucao = (
            f"a região {destaque['regiao']} teve a maior variação: de "
            f"{destaque['primeira_comp']} até {destaque['ultima_comp']}, "
            f"{direcao} {formatar_numero(abs(destaque['variacao']))} leitos SUS."
        )
    else:
        exemplo_evolucao = "é necessário ter mais de uma competência por região para comparar a variação."

    st.markdown("#### Gráfico de densidade")
    st.write(
        "Mostra a relação entre população municipal e quantidade de leitos SUS separada por região. "
        "Cada painel representa uma região do Brasil e cada ponto representa um município. "
        "Ao passar o mouse, aparecem o nome da cidade, UF, região, população e leitos SUS. "
        "Os eixos usam escala logarítmica porque há municípios muito pequenos e capitais muito grandes."
    )
    st.caption(f"Exemplo: {exemplo_densidade}")
    st.plotly_chart(grafico_densidade(df), use_container_width=True)

    st.markdown("#### Gráfico de barras")
    st.write(
        "Compara, por UF, os leitos SUS e os leitos existentes que não estão vinculados ao SUS. "
        "A barra empilhada permite ver tanto o total de leitos quanto a composição de cada estado."
    )
    st.caption(f"Exemplo: {exemplo_barras}")
    st.plotly_chart(grafico_barras(df), use_container_width=True)

    st.markdown("#### Gráfico de setores")
    st.write(
        "Mostra a participação de cada região no total de leitos SUS. "
        "Quanto maior o setor, maior a concentração regional de leitos disponíveis ao SUS."
    )
    st.caption(f"Exemplo: {exemplo_setores}")
    st.plotly_chart(grafico_setores(df), use_container_width=True)

    st.markdown("#### Gráfico de evolução")
    st.write(
        "Mostra a mudança mensal dos leitos SUS por região. Cada linha representa uma região, "
        "permitindo comparar se Norte, Nordeste, Sudeste, Sul e Centro-Oeste aumentaram, reduziram "
        "ou permaneceram estáveis ao longo das competências."
    )
    st.caption(f"Exemplo: {exemplo_evolucao}")
    st.plotly_chart(grafico_evolucao(evolucao_base), use_container_width=True)


def criar_metadados() -> list[dict[str, str]]:
    return [
        {
            "Coluna": "comp",
            "Descrição": "Competência mensal do arquivo de leitos.",
            "Uso no projeto": "Permite filtrar a base mais recente e montar a evolução mensal.",
        },
        {
            "Coluna": "regiao",
            "Descrição": "Região geográfica do estabelecimento.",
            "Uso no projeto": "Agrupamento regional dos leitos.",
        },
        {
            "Coluna": "uf",
            "Descrição": "Unidade Federativa.",
            "Uso no projeto": "Filtro lateral e comparação por estado.",
        },
        {
            "Coluna": "co_ibge",
            "Descrição": "Código IBGE do município.",
            "Uso no projeto": "Chave de ligação com a população do IBGE.",
        },
        {
            "Coluna": "municipio",
            "Descrição": "Nome do município.",
            "Uso no projeto": "Filtro, busca e análises municipais.",
        },
        {
            "Coluna": "cnes",
            "Descrição": "Código nacional do estabelecimento de saúde.",
            "Uso no projeto": "Identifica cada hospital/estabelecimento.",
        },
        {
            "Coluna": "nome_estabelecimento",
            "Descrição": "Nome fantasia do estabelecimento.",
            "Uso no projeto": "Busca textual e listagem principal.",
        },
        {
            "Coluna": "razao_social",
            "Descrição": "Razão social da instituição.",
            "Uso no projeto": "Complementa a busca por hospital.",
        },
        {
            "Coluna": "ds_tipo_unidade",
            "Descrição": "Tipo da unidade de saúde.",
            "Uso no projeto": "Contextualiza o perfil do estabelecimento.",
        },
        {
            "Coluna": "desc_natureza_juridica",
            "Descrição": "Natureza jurídica informada no CNES.",
            "Uso no projeto": "Ajuda a comentar fontes públicas, privadas e filantrópicas.",
        },
        {
            "Coluna": "leitos_existentes",
            "Descrição": "Total de leitos existentes.",
            "Uso no projeto": "Mede a capacidade total instalada.",
        },
        {
            "Coluna": "leitos_sus",
            "Descrição": "Total de leitos disponíveis ao SUS.",
            "Uso no projeto": "Indicador principal do painel.",
        },
        {
            "Coluna": "populacao",
            "Descrição": "População estimada do município.",
            "Uso no projeto": "Base para calcular leitos SUS por 10 mil habitantes.",
        },
    ]


def renderizar_nuvem_palavras() -> None:
    palavras = [
        (
            "SUS",
            "xl",
            "É a palavra central porque o painel analisa leitos disponíveis ao Sistema Único de Saúde.",
        ),
        (
            "Leitos",
            "xl",
            "Representa a capacidade hospitalar medida em leitos existentes e leitos SUS.",
        ),
        (
            "Município",
            "lg",
            "É usado para ligar estabelecimentos, população e comparação territorial.",
        ),
        (
            "UF",
            "md",
            "Permite comparar os estados e aplicar filtros geográficos.",
        ),
        (
            "População",
            "lg",
            "Entra no cálculo de leitos SUS por 10 mil habitantes.",
        ),
        (
            "CNES",
            "md",
            "Identifica oficialmente os estabelecimentos de saúde.",
        ),
        (
            "IBGE",
            "md",
            "Fornece o código municipal e a população usada no cruzamento de dados.",
        ),
        (
            "Ocupação",
            "md",
            "Aparece na simulação hospitalar para estimar pressão sobre os leitos.",
        ),
        (
            "Regulação",
            "sm",
            "Resume a ação operacional quando há fila, poucas vagas ou alta pressão.",
        ),
        (
            "Evolução",
            "sm",
            "Indica a análise por competência mensal ao longo do tempo.",
        ),
    ]

    tokens = " ".join(
        f"<span class='word-token word-{classe}'>{escape(palavra)}</span>"
        for palavra, classe, _ in palavras
    )

    st.markdown(f"<div class='word-cloud'>{tokens}</div>", unsafe_allow_html=True)

    explicacoes = "\n".join(
        f"- **{palavra}**: {justificativa}"
        for palavra, _, justificativa in palavras
    )
    st.markdown(explicacoes)


def renderizar_sobre(df, evolucao_base, competencia: str) -> None:
    st.subheader("Sobre o projeto")

    total_linhas = len(evolucao_base)
    total_colunas = len(df.columns)
    linhas_finais = len(df)
    total_municipios = df["co_ibge"].nunique()
    total_estabelecimentos = df["id_estabelecimento"].nunique()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Linhas originais", formatar_numero(total_linhas))
    c2.metric("Linhas finais", formatar_numero(linhas_finais))
    c3.metric("Colunas finais", formatar_numero(total_colunas))
    c4.metric("Competência", competencia)

    with st.expander("Nuvem de palavras", expanded=True):
        st.write(
            "A nuvem foi feita de forma simples, destacando termos que resumem o tema, "
            "as fontes e as principais análises do projeto."
        )
        renderizar_nuvem_palavras()

    with st.expander("Bibliotecas utilizadas e justificativa", expanded=True):
        st.write(
            "O projeto usa pandas para importação, limpeza e agrupamentos; Streamlit "
            "para construir o painel; Plotly para os gráficos da aba Gráficos; NumPy "
            "para cálculos da simulação; PySpark para demonstrar processamento em Big Data."
        )

    with st.expander("Fontes dos dados e tamanho da fonte", expanded=True):
        st.write(
            "A base de leitos vem de dados públicos do SUS/CNES. A população vem do IBGE. "
            "A coluna de natureza jurídica permite comentar estabelecimentos públicos, "
            "privados e filantrópicos dentro da base."
        )
        st.write(
            f"O volume usado no projeto tem {formatar_numero(total_linhas)} registros "
            f"históricos e {formatar_numero(linhas_finais)} registros após selecionar "
            f"a competência mais recente."
        )

        if "desc_natureza_juridica" in df.columns:
            natureza = (
                df.groupby("desc_natureza_juridica", as_index=False)
                .agg(estabelecimentos=("id_estabelecimento", "nunique"))
                .sort_values("estabelecimentos", ascending=False)
                .head(8)
            )
            st.dataframe(natureza, use_container_width=True, hide_index=True)

    with st.expander("Importação, renomeação e limpeza"):
        st.write(
            "Na importação, as colunas são padronizadas para letras minúsculas, sem "
            "acentos e com sublinhado. Isso evita erros em filtros, joins e comandos SQL."
        )
        st.code(
            "df = pd.read_csv(arquivo, sep=';', dtype=str)\n"
            "df.columns = [nome_coluna(c) for c in df.columns]",
            language="python",
        )
        st.write(
            "Também são convertidos campos numéricos, códigos IBGE e textos de região, "
            "UF e município. Depois disso, a base de leitos é cruzada com a população."
        )

    with st.expander("Metadados: dicionário de dados"):
        st.dataframe(criar_metadados(), use_container_width=True, hide_index=True)

    with st.expander("Primeiras linhas, colunas e dimensão"):
        st.write(
            "As 10 primeiras linhas ajudam a conferir se a importação e a limpeza "
            "mantiveram os campos principais corretamente."
        )
        st.dataframe(df.head(10), use_container_width=True, hide_index=True)

        st.write("Comando Python para mostrar os nomes das colunas:")
        st.code("df.columns.tolist()", language="python")
        st.write(", ".join(df.columns))

        st.write("Comando Python para mostrar a dimensão do dataset:")
        st.code("df.shape", language="python")
        st.write(f"Dimensão final: {df.shape[0]} linhas x {df.shape[1]} colunas.")

    with st.expander("Agrupamentos, mínimo e máximo"):
        st.write(
            "A categorização por região e UF resume a distribuição de leitos e facilita "
            "a comparação entre territórios."
        )
        st.code(
            "df.groupby(['regiao', 'uf'])[['leitos_existentes', 'leitos_sus']].sum()",
            language="python",
        )
        agrupado = (
            df.groupby(["regiao", "uf"], as_index=False)
            .agg(
                leitos_existentes=("leitos_existentes", "sum"),
                leitos_sus=("leitos_sus", "sum"),
                estabelecimentos=("id_estabelecimento", "nunique"),
            )
            .sort_values("leitos_sus", ascending=False)
        )
        st.dataframe(agrupado, use_container_width=True, hide_index=True)

        min_max = [
            {
                "Indicador": "Leitos existentes",
                "Mínimo": formatar_numero(df["leitos_existentes"].min()),
                "Máximo": formatar_numero(df["leitos_existentes"].max()),
            },
            {
                "Indicador": "Leitos SUS",
                "Mínimo": formatar_numero(df["leitos_sus"].min()),
                "Máximo": formatar_numero(df["leitos_sus"].max()),
            },
            {
                "Indicador": "População municipal",
                "Mínimo": formatar_numero(df["populacao"].min()),
                "Máximo": formatar_numero(df["populacao"].max()),
            },
        ]
        st.dataframe(min_max, use_container_width=True, hide_index=True)

    with st.expander("Outliers e manipulação com Spark SQL"):
        q1 = df["leitos_sus"].quantile(0.25)
        q3 = df["leitos_sus"].quantile(0.75)
        limite_superior = q3 + 1.5 * (q3 - q1)
        outliers = df[df["leitos_sus"] > limite_superior]

        st.write(
            "Os outliers são estabelecimentos com quantidade de leitos SUS muito acima "
            "do padrão da maioria. Eles são identificados para comentário e cuidado na "
            "interpretação, porque hospitais muito grandes podem distorcer médias e escalas."
        )
        st.write(
            f"Pelo critério IQR, foram identificados {formatar_numero(len(outliers))} "
            f"registros acima de {formatar_decimal(limite_superior)} leitos SUS."
        )

        st.write("Exemplo de busca com SQL no Spark:")
        st.code(
            "base.createOrReplaceTempView('leitos')\n"
            "spark.sql('''\n"
            "    SELECT uf, SUM(leitos_sus) AS leitos_sus\n"
            "    FROM leitos\n"
            "    GROUP BY uf\n"
            "    ORDER BY leitos_sus DESC\n"
            "''').show()",
            language="python",
        )

    with st.expander("Mineração de dados e uso de IA"):
        st.write(
            "A mineração de dados aparece na busca por padrões entre território, tipo de "
            "unidade, quantidade de leitos e pressão simulada. Regras de associação podem "
            "ajudar a encontrar combinações recorrentes, por exemplo: região, tipo de unidade "
            "e maior dependência de leitos SUS."
        )
        st.write(
            "O uso de IA foi aplicado como apoio para organizar o código, conforme os csv's para otimizar o tempo, tendo em vista que são centenas de linhas. "
            "numeros e analises continuam baseadas nos dados públicos carregados no projeto."
        )


def renderizar_card_simulacao(linha) -> None:
    cor_status = STATUS_CORES.get(linha["status"], "#94a3b8")

    with st.container(border=True):
        st.markdown(f"### {linha['nome_estabelecimento']}")
        st.caption(f"{linha['municipio']} / {linha['uf']}")

        colunas = st.columns(5)
        colunas[0].metric("Leitos SUS", formatar_numero(linha["leitos_sus"]))
        colunas[1].metric("Ocupação", f"{formatar_decimal(linha['ocupacao_pct'])}%")
        colunas[2].metric("Fila", formatar_numero(linha["fila"]))
        colunas[3].metric("Vagas em 6h", formatar_numero(linha["vagas_6h"]))
        colunas[4].markdown(
            (
                f"<div class='status-pill' style='border-color:{cor_status};"
                f"color:{cor_status}'>{linha['status']}</div>"
            ),
            unsafe_allow_html=True,
        )

        st.caption(linha["acao"])


def renderizar_resumo_simulacao(simulacao) -> None:
    ordem = ["Estável", "Atenção", "Crítico", "Sem SUS"]
    contagem = simulacao["status"].value_counts()
    colunas = st.columns(len(ordem))

    for coluna, status in zip(colunas, ordem):
        coluna.metric(status, formatar_numero(contagem.get(status, 0)))


def selecionar_resultados_simulacao(simulacao, limite: int):
    cotas = {
        "Crítico": 7,
        "Atenção": 7,
        "Estável": 7,
        "Sem SUS": 4,
    }
    partes = []
    indices_usados = set()

    for status, quantidade in cotas.items():
        parte = simulacao[simulacao["status"].eq(status)].head(quantidade)
        partes.append(parte)
        indices_usados.update(parte.index)

    resultado = simulacao.iloc[0:0] if not partes else pd.concat(partes)

    if len(resultado) < limite:
        restante = simulacao[~simulacao.index.isin(indices_usados)]
        resultado = pd.concat([resultado, restante.head(limite - len(resultado))])

    return resultado.head(limite)


def renderizar_simulacao(df) -> None:
    st.subheader("Simulação hospitalar")

    st.caption(
        "Ocupação, fila e vagas são valores simulados para fins acadêmicos. "
        "A variação usa capacidade SUS, população municipal, pressão territorial "
        "e um perfil fixo por hospital."
    )

    cenarios = list(PRESSAO_CENARIOS.keys())
    cenario = st.selectbox(
        "Cenário da simulação",
        cenarios,
        index=cenarios.index("Alta demanda"),
    )

    hospital = st.text_input("Pesquisar hospital")
    resultado = pesquisar_hospital(df, hospital)

    if resultado.empty:
        st.warning("Nenhum hospital encontrado.")
        return

    simulacao = gerar_status_leitos(calcular_ocupacao(resultado, cenario))

    renderizar_resumo_simulacao(simulacao)

    status_opcoes = ["Todos", "Estável", "Atenção", "Crítico", "Sem SUS"]
    if hasattr(st, "segmented_control"):
        status_sel = st.segmented_control(
            "Filtrar por status",
            status_opcoes,
            default="Todos",
        )
    else:
        status_sel = st.radio(
            "Filtrar por status",
            status_opcoes,
            horizontal=True,
        )

    if status_sel and status_sel != "Todos":
        simulacao = simulacao[simulacao["status"].eq(status_sel)]

    if simulacao.empty:
        st.warning("Nenhum hospital encontrado para o status selecionado.")
        return

    limite_exibicao = 25
    exibicao = (
        selecionar_resultados_simulacao(simulacao, limite_exibicao)
        if status_sel == "Todos"
        else simulacao.head(limite_exibicao)
    )

    if len(simulacao) > limite_exibicao:
        st.caption(
            f"Exibindo {len(exibicao)} de {formatar_numero(len(simulacao))} resultados da simulação."
        )

    for _, linha in exibicao.iterrows():
        renderizar_card_simulacao(linha)


def main() -> None:
    configurar_pagina()

    df, evolucao_base, competencia_mais_recente = carregar_base_app()
    df_filtrado = aplicar_filtros(df)
    kpis = calcular_kpis(df_filtrado)

    renderizar_cabecalho(competencia_mais_recente)
    renderizar_metricas(kpis)

    aba_graficos, aba_simulacao, aba_sobre = st.tabs(
        ["Gráficos", "Simulação", "Sobre"]
    )

    with aba_graficos:
        renderizar_graficos(df_filtrado, evolucao_base)

    with aba_simulacao:
        renderizar_simulacao(df_filtrado)

    with aba_sobre:
        renderizar_sobre(df, evolucao_base, competencia_mais_recente)

    st.divider()
    st.caption("Projeto acadêmico com dados públicos do SUS e IBGE.")


if __name__ == "__main__":
    main()
