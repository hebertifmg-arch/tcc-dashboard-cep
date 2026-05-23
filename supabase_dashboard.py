"""
============================================================================
 Dashboard CEP - Controle Estatístico de Processo
 TCC IFMG Sabará - Hebert Emmanuel Rocha Peluso
 ----------------------------------------------------------------------------
 Versão pronta para deploy no Streamlit Community Cloud.
 Credenciais lidas via st.secrets (NÃO hardcoded).
============================================================================
"""

import streamlit as st
from supabase import create_client
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from scipy.stats import norm
from datetime import datetime, timedelta

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
# 2. CONEXÃO SUPABASE - credenciais via st.secrets
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
# 3. SIDEBAR
# =============================================================================
st.sidebar.header("⚙️ Configurações")

st.sidebar.subheader("Filtros de período")
hoje = datetime.now().date()
data_inicio = st.sidebar.date_input("Data início", value=hoje - timedelta(days=1))
data_fim    = st.sidebar.date_input("Data fim",    value=hoje)

st.sidebar.subheader("Limites de especificação (mm)")
LIE = st.sidebar.number_input("LIE (Limite Inferior)", value=28.0, step=0.1, format="%.2f")
LSE = st.sidebar.number_input("LSE (Limite Superior)", value=32.0, step=0.1, format="%.2f")

if LIE >= LSE:
    st.sidebar.error("⚠️ LIE deve ser menor que LSE")
    st.stop()

st.sidebar.subheader("Atualização")
auto_refresh = st.sidebar.checkbox("Auto-refresh (10s)", value=False)
if st.sidebar.button("🔄 Atualizar agora"):
    st.cache_data.clear()
    st.rerun()

# =============================================================================
# 4. CARREGAMENTO
# =============================================================================
@st.cache_data(ttl=10)
def carregar_dados(d_ini, d_fim):
    inicio_iso = f"{d_ini}T00:00:00+00:00"
    fim_iso    = f"{d_fim}T23:59:59+00:00"

    response = (
        sb.table("leituras")
        .select("valor_bruto, tensao, medida_mm, uptime_s, timestamp")
        .gte("timestamp", inicio_iso)
        .lte("timestamp", fim_iso)
        .order("timestamp", desc=False)
        .execute()
    )

    if not response.data:
        return pd.DataFrame()

    df = pd.DataFrame(response.data)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df["timestamp"] = df["timestamp"].dt.tz_convert("America/Sao_Paulo")
    return df

df = carregar_dados(data_inicio, data_fim)

if df.empty:
    st.warning(
        "Nenhuma medição encontrada no período selecionado. "
        "Verifique se a ponte e o ESP32 estão rodando."
    )
    st.stop()

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
# 10. TABELA DE NÃO CONFORMIDADES
# =============================================================================
st.subheader("⚠️ Registro de Não Conformidades")
if n_rejeitos > 0:
    tabela = df[df["status"] == "REJEITADO"][
        ["timestamp", "medida_mm", "valor_bruto", "tensao", "status"]
    ].copy()
    tabela["timestamp"] = tabela["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S")
    tabela.columns = ["Data/Hora", "Medida (mm)", "ADC bruto", "Tensão (V)", "Status"]
    st.dataframe(tabela, use_container_width=True, hide_index=True)
    csv = tabela.to_csv(index=False).encode("utf-8")
    st.download_button("📥 Baixar CSV", csv, "nao_conformidades.csv", "text/csv")
else:
    st.success("✅ Nenhuma peça rejeitada no período selecionado.")

# =============================================================================
# 11. AUTO-REFRESH
# =============================================================================
if auto_refresh:
    import time
    time.sleep(10)
    st.rerun()
