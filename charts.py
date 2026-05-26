import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


REGIAO_CORES = {
    "NORTE": "#38bdf8",
    "NORDESTE": "#f59e0b",
    "SUDESTE": "#22c55e",
    "SUL": "#a78bfa",
    "CENTRO-OESTE": "#ef4444",
}



ORDEM_REGIOES = [ "NORTE", "NORDESTE", "SUDESTE", "SUL", "CENTRO-OESTE"]


def aplicar_layout(fig: go.Figure, altura: int = 430, titulo: str | None = None) -> go.Figure:
    fig.update_layout(
        template="plotly_dark",
        height=altura,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#e5e7eb"),
        margin=dict(l=20, r=20, t=65, b=35),
        legend=dict(orientation="h", y=1.08),
    )

    if titulo:
        fig.update_layout(title=dict(text=titulo, x=0.02, xanchor="left"))

    return fig


def figura_vazia(mensagem: str, altura: int = 430) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(
        text=mensagem,
        x=0.5,
        y=0.5,
        xref="paper",
        yref="paper",
        showarrow=False,
        font=dict(size=15, color="#cbd5e1"),
    )

    return aplicar_layout(fig, altura=altura)


def grafico_densidade(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return figura_vazia("Nenhum dado disponível para o gráfico municipal.")

    municipios = (
        df.groupby(["regiao", "municipio", "uf", "co_ibge"], as_index=False)
        .agg(
            populacao=("populacao", "max"),
            leitos_sus=("leitos_sus", "sum"),
        )
    )

    municipios = municipios[municipios["populacao"] > 0].copy()
    if municipios.empty:
        return figura_vazia("Não há população associada aos municípios filtrados.")

    regioes = [regiao for regiao in ORDEM_REGIOES if regiao in municipios["regiao"].unique()]
    altura = 720 if len(regioes) > 3 else 520

    municipios["leitos_sus_plot"] = municipios["leitos_sus"] + 1
    municipios["tamanho_ponto"] = municipios["leitos_sus"].clip(lower=1)

    fig = px.scatter(
        municipios,
        x="populacao",
        y="leitos_sus_plot",
        color="regiao",
        size="tamanho_ponto",
        size_max=18,
        opacity=0.72,
        log_x=True,
        log_y=True,
        facet_col="regiao",
        facet_col_wrap=3,
        category_orders={"regiao": regioes},
        labels={
            "populacao": "População",
            "leitos_sus_plot": "Leitos SUS (+1, escala log)",
            "regiao": "Região",
        },
        color_discrete_map=REGIAO_CORES,
        custom_data=["municipio", "uf", "regiao", "populacao", "leitos_sus"],
    )
    fig.for_each_annotation(lambda item: item.update(text=item.text.split("=")[-1]))
    fig.update_traces(
        marker=dict(line=dict(width=0.4, color="#111827")),
        hovertemplate=(
            "<b>%{customdata[0]} / %{customdata[1]}</b><br>"
            "Região: %{customdata[2]}<br>"
            "População: %{customdata[3]:,.0f}<br>"
            "Leitos SUS: %{customdata[4]:,.0f}"
            "<extra></extra>"
        ),
    )

    return aplicar_layout(
        fig,
        altura=altura,
        titulo="Municípios por região: população x leitos SUS",
    )


def grafico_barras(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return figura_vazia("Nenhum dado disponível para barras por UF.")

    resumo = (
        df.groupby(["regiao", "uf"], as_index=False)
        .agg(
            leitos_sus=("leitos_sus", "sum"),
            existentes_nao_sus=("existentes_nao_sus", "sum"),
        )
    )

    barras = resumo.melt(
        id_vars=["regiao", "uf"],
        value_vars=["leitos_sus", "existentes_nao_sus"],
        var_name="tipo",
        value_name="leitos",
    )

    barras["tipo"] = barras["tipo"].replace(
        {
            "leitos_sus": "Leitos SUS",
            "existentes_nao_sus": "Não SUS",
        }
    )

    fig = px.bar(
        barras,
        x="uf",
        y="leitos",
        color="tipo",
        text="leitos",
        barmode="stack",
        labels={
            "uf": "UF",
            "leitos": "Quantidade",
            "tipo": "Categoria",
        },
        color_discrete_map={
            "Leitos SUS": "#16a34a",
            "Não SUS": "#f59e0b",
        },
    )
    fig.update_traces(texttemplate="%{text:.0f}", textposition="inside")

    return aplicar_layout(fig, titulo="Leitos SUS e não SUS por UF")


def grafico_setores(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return figura_vazia("Nenhum dado disponível para distribuição regional.")

    resumo = (
        df.groupby("regiao", as_index=False)
        .agg(leitos_sus=("leitos_sus", "sum"))
    )
    resumo = resumo[resumo["leitos_sus"] > 0]

    if resumo.empty:
        return figura_vazia("Não há leitos SUS no recorte filtrado.")

    fig = px.pie(
        resumo,
        names="regiao",
        values="leitos_sus",
        hole=0.5,
        labels={
            "regiao": "Região",
            "leitos_sus": "Leitos SUS",
        },
        color="regiao",
        color_discrete_map=REGIAO_CORES,
    )

    return aplicar_layout(fig, titulo="Distribuição regional dos leitos SUS")


def grafico_evolucao(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return figura_vazia("Nenhum dado disponível para evolução mensal.")

    colunas_grupo = ["comp", "regiao"] if "regiao" in df.columns else ["comp"]
    evolucao = (
        df.groupby(colunas_grupo, as_index=False)
        .agg(leitos_sus=("leitos_sus", "sum"))
        .sort_values(colunas_grupo)
    )

    if evolucao.empty:
        return figura_vazia("Não há competências para exibir na evolução.")

    if "regiao" not in evolucao.columns:
        fig = px.line(
            evolucao,
            x="comp",
            y="leitos_sus",
            markers=True,
            labels={
                "comp": "Competência",
                "leitos_sus": "Leitos SUS",
            },
        )
    else:
        regioes = [regiao for regiao in ORDEM_REGIOES if regiao in evolucao["regiao"].unique()]
        fig = px.line(
            evolucao,
            x="comp",
            y="leitos_sus",
            color="regiao",
            markers=True,
            category_orders={"regiao": regioes},
            labels={
                "comp": "Competência",
                "leitos_sus": "Leitos SUS",
                "regiao": "Região",
            },
            color_discrete_map=REGIAO_CORES,
        )

    return aplicar_layout(fig, titulo="Evolução mensal de leitos SUS por região")
