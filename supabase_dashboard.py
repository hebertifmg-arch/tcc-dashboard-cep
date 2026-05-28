"""
============================================================================
 Dashboard CEP - Controle Estatístico de Processo
 TCC IFMG Sabará - Hebert Emmanuel Rocha Peluso
 ----------------------------------------------------------------------------
 Versão com filtro de data + hora e limite ampliado de leitura (50000).
============================================================================
"""

import streamlit as st
from supabase import create_client
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from scipy.stats import norm
from datetime import datetime, timedelta, time

# =============================================================================
# 1. CONFIGURAÇÃO
# =============================================================================
st.set_page_config(
    page_title="Dashboard CEP - Paquímetro IoT",
    page_icon="📏",
    layout="wide",
)

st.title("📏 Dashboard CEP - Paquímetro IoT")
st.caption("TCC - Hebert Peluso | IFMG Sabará | Dados via Supabase (PostgreSQL)")

# =============================================================================
# 2. CONEXÃO SUPABASE
# =============================================================================
try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
except KeyError as e:
    st.error(
        f"❌ Credencial faltando: {e}\n\n"
        "Configure em **Settings → Secrets** no Streamlit Cloud, ou crie um "
        "arquivo `.streamlit/secrets.toml` local com:\n\n"
        "```\nSUPABASE_URL = \"https://...supabase.co\"\n"
        "SUPABASE_KEY = \"sb_publishable_...\"\n```"
    )
    st.stop()

@st.cache_resource
def conectar_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

sb = conectar_supabase()

# =============================================================================
# 3. SIDEBAR - FILTROS GERAIS
# =============================================================================
st.sidebar.header("⚙️ Configurações")

st.sidebar.subheader("📅 Filtros de período")

agora = datetime.now()
hoje = agora.date()
ontem = hoje - timedelta(days=1)

# --- Inicialização do session_state (apenas na primeira execução) ---
if "data_ini" not in st.session_state:
    st.session_state.data_ini = ontem
    st.session_state.hora_ini = time(0, 0)
    st.session_state.data_fim = hoje
    st.session_state.hora_fim = time(23, 59)

# --- Botões de atalho ANTES dos widgets (assim podemos alterar session_state) ---
st.sidebar.caption("Atalhos rápidos:")
col_a1, col_a2, col_a3 = st.sidebar.columns(3)

def aplicar_atalho(novo_ini: datetime, novo_fim: datetime):
    st.session_state.data_ini = novo_ini.date()
    st.session_state.hora_ini = novo_ini.time().replace(second=0, microsecond=0)
    st.session_state.data_fim = novo_fim.date()
    st.session_state.hora_fim = novo_fim.time().replace(second=0, microsecond=0)

if col_a1.button("Última 1h", use_container_width=True):
    aplicar_atalho(agora - timedelta(hours=1), agora)
    st.rerun()
if col_a2.button("Hoje", use_container_width=True):
    aplicar_atalho(
        datetime.combine(hoje, time(0, 0)),
        datetime.combine(hoje, time(23, 59))
    )
    st.rerun()
if col_a3.button("7 dias", use_container_width=True):
    aplicar_atalho(
        datetime.combine(hoje - timedelta(days=7), time(0, 0)),
        datetime.combine(hoje, time(23, 59))
    )
    st.rerun()

# --- Widgets de data/hora ---
col_d_ini, col_h_ini = st.sidebar.columns([3, 2])
with col_d_ini:
    data_inicio = st.date_input("Data início", key="data_ini")
with col_h_ini:
    hora_inicio = st.time_input("Hora", key="hora_ini", step=60)

col_d_fim, col_h_fim = st.sidebar.columns([3, 2])
with col_d_fim:
    data_fim = st.date_input("Data fim", key="data_fim")
with col_h_fim:
    hora_fim = st.time_input("Hora", key="hora_fim", step=60)

dt_inicio = datetime.combine(data_inicio, hora_inicio)
dt_fim    = datetime.combine(data_fim, hora_fim)

if dt_inicio >= dt_fim:
    st.sidebar.error("⚠️ Data/hora de início deve ser anterior à de fim")
    st.stop()

st.sidebar.subheader("📐 Limites de especificação (mm)")
LIE = st.sidebar.number_input("LIE (Limite Inferior)", value=28.0, step=0.1, format="%.2f")
LSE = st.sidebar.number_input("LSE (Limite Superior)", value=32.0, step=0.1, format="%.2f")

if LIE >= LSE:
    st.sidebar.error("⚠️ LIE deve ser menor que LSE")
    st.stop()

st.sidebar.subheader("🔄 Atualização")
auto_refresh = st.sidebar.checkbox("Auto-refresh (10s)", value=False)
if st.sidebar.button("🔄 Atualizar agora", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

# =============================================================================
# 4. CARREGAMENTO
# =============================================================================
@st.cache_data(ttl=10)
def carregar_dados(dt_ini: datetime, dt_fim: datetime):
    inicio_iso = dt_ini.strftime("%Y-%m-%dT%H:%M:%S-03:00")
    fim_iso    = dt_fim.strftime("%Y-%m-%dT%H:%M:%S-03:00")

    response = (
        sb.table("leituras")
        .select("valor_bruto, tensao, medida_mm, uptime_s, timestamp")
        .gte("timestamp", inicio_iso)
        .lte("timestamp", fim_iso)
        .order("timestamp", desc=False)
        .limit(50000)   # << contorna o limite default do PostgREST (1000)
        .execute()
    )

    if not response.data:
        return pd.DataFrame()

    df = pd.DataFrame(response.data)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df["timestamp"] = df["timestamp"].dt.tz_convert("America/Sao_Paulo")
    return df

df = carregar_dados(dt_inicio, dt_fim)

# Cabeçalho com info do período
st.info(
    f"📊 Período: **{dt_inicio.strftime('%d/%m/%Y %H:%M')}** até **{dt_fim.strftime('%d/%m/%Y %H:%M')}**"
)

if df.empty:
    st.warning(
        "Nenhuma medição encontrada no período selecionado. "
        "Verifique se a ponte e o ESP32 estão rodando, ou amplie a janela temporal."
    )
    st.stop()

# Aviso se atingir o teto da consulta (provável necessidade de paginação)
if len(df) >= 50000:
    st.warning(
        f"⚠️ A consulta atingiu o teto de **{len(df)} registros**. "
        "Pode haver mais dados no período. Refine o filtro ou implemente paginação."
    )

# =============================================================================
# 5. CLASSIFICAÇÃO
# =============================================================================
df["status"] = np.where(
    (df["medida_mm"] >= LIE) & (df["medida_mm"] <= LSE),
    "OK", "REJEITADO"
)

# =============================================================================
# 6. INDICADORES CEP
# =============================================================================
medidas = df["medida_mm"].values
n = len(medidas)
media = medidas.mean()
desvio = medidas.std(ddof=1) if n > 1 else 0.0

if desvio > 0:
    cp  = (LSE - LIE) / (6 * desvio)
    cpu = (LSE - media) / (3 * desvio)
    cpl = (media - LIE) / (3 * desvio)
    cpk = min(cpu, cpl)
else:
    cp = cpk = float("nan")

LSC = media + 3 * desvio
LIC = media - 3 * desvio
n_rejeitos = (df["status"] == "REJEITADO").sum()
pct_rejeito = 100 * n_rejeitos / n if n > 0 else 0.0

# =============================================================================
# 7. KPIs
# =============================================================================
col1, col2, col3, col4, col5, col6 = st.columns(6)
col1.metric("Total medições", f"{n}")
col2.metric("Média (mm)", f"{media:.3f}")
col3.metric("Desvio padrão", f"{desvio:.4f}")
col4.metric("Cp",  f"{cp:.2f}"  if not np.isnan(cp)  else "—")
col5.metric("Cpk", f"{cpk:.2f}" if not np.isnan(cpk) else "—",
            delta="Capaz" if cpk >= 1.33 else ("Marginal" if cpk >= 1.0 else "Incapaz"),
            delta_color="normal" if cpk >= 1.33 else "inverse")
col6.metric("Rejeitos", f"{n_rejeitos} ({pct_rejeito:.1f}%)",
            delta_color="inverse")

st.divider()

# =============================================================================
# 8. GRÁFICO SHEWHART
# =============================================================================
st.subheader("📈 Gráfico de Controle (Shewhart)")

fig_ctrl = go.Figure()
df_ok  = df[df["status"] == "OK"]
df_rej = df[df["status"] == "REJEITADO"]

fig_ctrl.add_trace(go.Scatter(
    x=df["timestamp"], y=df["medida_mm"],
    mode="lines", name="Tendência",
    line=dict(color="lightgray", width=1), showlegend=False,
))
fig_ctrl.add_trace(go.Scatter(
    x=df_ok["timestamp"], y=df_ok["medida_mm"],
    mode="markers", name="Aprovadas",
    marker=dict(color="green", size=7),
))
fig_ctrl.add_trace(go.Scatter(
    x=df_rej["timestamp"], y=df_rej["medida_mm"],
    mode="markers", name="Rejeitadas",
    marker=dict(color="red", size=10, symbol="x"),
))

fig_ctrl.add_hline(y=LSE, line=dict(color="blue", dash="dash"),
                   annotation_text=f"LSE = {LSE:.2f}", annotation_position="top right")
fig_ctrl.add_hline(y=LIE, line=dict(color="blue", dash="dash"),
                   annotation_text=f"LIE = {LIE:.2f}", annotation_position="bottom right")
fig_ctrl.add_hline(y=media, line=dict(color="black", dash="solid"),
                   annotation_text=f"Média = {media:.3f}", annotation_position="top left")
fig_ctrl.add_hline(y=LSC, line=dict(color="orange", dash="dot"),
                   annotation_text=f"LSC = {LSC:.3f}", annotation_position="top right")
fig_ctrl.add_hline(y=LIC, line=dict(color="orange", dash="dot"),
                   annotation_text=f"LIC = {LIC:.3f}", annotation_position="bottom right")

fig_ctrl.update_layout(
    xaxis_title="Tempo", yaxis_title="Medida (mm)", height=450,
    hovermode="x unified",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
)
st.plotly_chart(fig_ctrl, use_container_width=True)

# =============================================================================
# 9. HISTOGRAMA
# =============================================================================
col_hist, col_info = st.columns([2, 1])

with col_hist:
    st.subheader("📊 Distribuição das Medições")
    fig_hist = go.Figure()
    fig_hist.add_trace(go.Histogram(
        x=medidas, nbinsx=30, name="Frequência",
        marker_color="steelblue", opacity=0.75, histnorm="probability density",
    ))
    if desvio > 0 and n > 1:
        x_curve = np.linspace(medidas.min(), medidas.max(), 200)
        y_curve = norm.pdf(x_curve, loc=media, scale=desvio)
        fig_hist.add_trace(go.Scatter(
            x=x_curve, y=y_curve, mode="lines", name="Normal teórica",
            line=dict(color="darkred", width=2),
        ))
    fig_hist.add_vline(x=LSE, line=dict(color="blue", dash="dash"), annotation_text="LSE")
    fig_hist.add_vline(x=LIE, line=dict(color="blue", dash="dash"), annotation_text="LIE")
    fig_hist.add_vline(x=media, line=dict(color="black"), annotation_text="Média")
    fig_hist.update_layout(
        xaxis_title="Medida (mm)", yaxis_title="Densidade", height=400, bargap=0.05,
    )
    st.plotly_chart(fig_hist, use_container_width=True)

with col_info:
    st.subheader("ℹ️ Interpretação")
    if not np.isnan(cpk):
        if cpk >= 1.67:
            st.success(f"**Processo excelente** (Cpk = {cpk:.2f} ≥ 1,67)")
        elif cpk >= 1.33:
            st.success(f"**Processo capaz** (Cpk = {cpk:.2f} ≥ 1,33)")
        elif cpk >= 1.0:
            st.warning(f"**Capacidade marginal** (1,00 ≤ Cpk = {cpk:.2f} < 1,33)")
        else:
            st.error(f"**Processo incapaz** (Cpk = {cpk:.2f} < 1,00)")

    st.markdown(f"""
    **Resumo estatístico**
    - Amostras: **{n}**
    - Média: **{media:.3f} mm**
    - σ (s): **{desvio:.4f} mm**
    - LSC (+3σ): **{LSC:.3f} mm**
    - LIC (−3σ): **{LIC:.3f} mm**
    - Amplitude: **{medidas.max() - medidas.min():.3f} mm**
    """)

st.divider()

# =============================================================================
# 10. TABELA DE NÃO CONFORMIDADES - com filtro adicional
# =============================================================================
st.subheader("⚠️ Registro de Não Conformidades")

rejeitos_df = df[df["status"] == "REJEITADO"].copy()

if rejeitos_df.empty:
    st.success("✅ Nenhuma peça rejeitada no período selecionado.")
else:
    with st.expander("🔎 Filtrar não conformidades (refinamento)", expanded=False):
        st.caption(
            f"Total de rejeitos no período principal: **{len(rejeitos_df)}**. "
            "Use os filtros abaixo para refinar a lista."
        )

        rej_min = rejeitos_df["timestamp"].min().to_pydatetime()
        rej_max = rejeitos_df["timestamp"].max().to_pydatetime()

        col_rf1, col_rf2 = st.columns(2)
        with col_rf1:
            data_rej_ini = st.date_input(
                "Data início (refinar)",
                value=rej_min.date(),
                key="rej_data_ini",
                min_value=rej_min.date(),
                max_value=rej_max.date(),
            )
            hora_rej_ini = st.time_input(
                "Hora início (refinar)",
                value=rej_min.time().replace(second=0, microsecond=0),
                key="rej_hora_ini",
                step=60,
            )
        with col_rf2:
            data_rej_fim = st.date_input(
                "Data fim (refinar)",
                value=rej_max.date(),
                key="rej_data_fim",
                min_value=rej_min.date(),
                max_value=rej_max.date(),
            )
            hora_rej_fim = st.time_input(
                "Hora fim (refinar)",
                value=rej_max.time().replace(second=0, microsecond=0),
                key="rej_hora_fim",
                step=60,
            )

        col_rf3, col_rf4 = st.columns(2)
        with col_rf3:
            medida_min_filter = st.number_input(
                "Medida mínima (mm)",
                value=float(rejeitos_df["medida_mm"].min()),
                step=0.1, format="%.3f",
                key="rej_medida_min"
            )
        with col_rf4:
            medida_max_filter = st.number_input(
                "Medida máxima (mm)",
                value=float(rejeitos_df["medida_mm"].max()),
                step=0.1, format="%.3f",
                key="rej_medida_max"
            )

    dt_rej_ini = pd.Timestamp(datetime.combine(data_rej_ini, hora_rej_ini), tz="America/Sao_Paulo")
    dt_rej_fim = pd.Timestamp(datetime.combine(data_rej_fim, hora_rej_fim), tz="America/Sao_Paulo")

    rejeitos_filtrados = rejeitos_df[
        (rejeitos_df["timestamp"] >= dt_rej_ini) &
        (rejeitos_df["timestamp"] <= dt_rej_fim) &
        (rejeitos_df["medida_mm"] >= medida_min_filter) &
        (rejeitos_df["medida_mm"] <= medida_max_filter)
    ]

    col_c1, col_c2 = st.columns(2)
    col_c1.metric("Rejeitos exibidos", f"{len(rejeitos_filtrados)} de {len(rejeitos_df)}")
    if len(rejeitos_filtrados) > 0:
        col_c2.metric("Medida média dos rejeitos", f"{rejeitos_filtrados['medida_mm'].mean():.3f} mm")

    if rejeitos_filtrados.empty:
        st.warning("Nenhum rejeito corresponde aos filtros aplicados.")
    else:
        tabela = rejeitos_filtrados[
            ["timestamp", "medida_mm", "valor_bruto", "tensao", "status"]
        ].copy()
        tabela["timestamp"] = tabela["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S")
        tabela.columns = ["Data/Hora", "Medida (mm)", "ADC bruto", "Tensão (V)", "Status"]
        st.dataframe(tabela, use_container_width=True, hide_index=True)

        csv = tabela.to_csv(index=False).encode("utf-8")
        st.download_button(
            "📥 Baixar CSV", csv,
            f"nao_conformidades_{data_rej_ini}_{data_rej_fim}.csv",
            "text/csv"
        )

# =============================================================================
# 11. AUTO-REFRESH
# =============================================================================
if auto_refresh:
    import time as _time
    _time.sleep(10)
    st.rerun()
