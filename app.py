import streamlit as st
import numpy as np
import pandas as pd
import scipy.optimize as opt
import plotly.graph_objects as go
import plotly.express as px
import io

st.set_page_config(
    page_title="Modelador de Tarifas PTESA - Recurrente e Inicial",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("⚡ Modelador Tarifario Integrado (Recurrente e Inicial)")
st.markdown("""
Esta herramienta analiza el impacto del nuevo esquema tarifario sobre tu cartera actual:
* **Recurrente:** Optimiza $P_{\text{base}}$ y la bolsa $T_1$ ajustándose a la facturación real actual (`valor cobrado`) y respetando el cobro mínimo ($MCB_{\text{piso}}$).
* **Inicial (Upfront):** Simula el cobro de entrada ($ILF + ICLF$) que le correspondería a cada cliente actual si contratara la capacidad equivalente hoy como nuevo cliente.
""")

def load_and_standardize_data(uploaded_file):
    """Carga y estandariza los datos de Excel/CSV a columnas homogéneas."""
    if uploaded_file is not None:
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)
    else:
        # Generar dataset sintético con la estructura del usuario
        np.random.seed(42)
        n = 45
        productos = np.random.choice(["Pasarela Pagos", "Corresponsales", "Billetera Virtual"], size=n)
        txns = np.random.lognormal(mean=7.5, sigma=1.2, size=n).astype(int) + 100
        valores = txns * np.random.uniform(1200, 2400, size=n) + 800000
        df = pd.DataFrame({
            "producto": productos,
            "# txn": txns,
            "valor cobrado": valores
        })

    # Mapeo flexible de columnas para evitar fallos por variaciones tipográficas
    col_map = {}
    for col in df.columns:
        c_clean = str(col).strip().lower()
        if "prod" in c_clean:
            col_map[col] = "producto"
        elif "txn" in c_clean or "transacc" in c_clean or "vol" in c_clean:
            col_map[col] = "# txn"
        elif "valor" in c_clean or "cobrad" in c_clean or "factur" in c_clean or "rec" in c_clean:
            col_map[col] = "valor cobrado"

    df = df.rename(columns=col_map)
    
    # Validaciones mínimas
    if "producto" not in df.columns:
        df["producto"] = "General"
    if "# txn" not in df.columns:
        df["# txn"] = 1000
    if "valor cobrado" not in df.columns:
        df["valor cobrado"] = 1500000.0
        
    df["# txn"] = pd.to_numeric(df["# txn"], errors='coerce').fillna(1).astype(int)
    df["valor cobrado"] = pd.to_numeric(df["valor cobrado"], errors='coerce').fillna(0.0)
    
    # Identificador de registro/cliente
    df["ID_Cliente"] = [f"Cliente_{i+1}" for i in range(len(df))]
    return df

st.sidebar.header("📁 1. Ingesta de Datos")
uploaded_file = st.sidebar.file_uploader("Subir `producto_volumen_facturado.xlsx` / CSV", type=["xlsx", "csv"])

df_raw = load_and_standardize_data(uploaded_file)

# Filtro por Producto
st.sidebar.header("🎯 2. Filtro por Producto")
lista_productos = ["TODOS"] + sorted(df_raw["producto"].unique().tolist())
prod_seleccionado = st.sidebar.selectbox("Seleccionar Línea de Producto", lista_productos)

if prod_seleccionado != "TODOS":
    df_work = df_raw[df_raw["producto"] == prod_seleccionado].copy().reset_index(drop=True)
else:
    df_work = df_raw.copy().reset_index(drop=True)

st.sidebar.header("⚙️ 3. Parámetros Globales de Bolsas")
D_max = st.sidebar.slider("Descuento Máximo ($D_{\\max}$)", 0.05, 0.50, 0.30, 0.01)
k_sens = st.sidebar.slider("Sensibilidad ($k$)", 100, 3000, 500, 50)

st.sidebar.header("🔄 4. Modelo Recurrente ($MCLF$)")
MCB_piso = st.sidebar.number_input("Piso Mínimo Mensual ($MCB_{\\piso}$ COP)", value=1000000, step=100000)
Rev_target_pct = st.sidebar.slider("Meta % Facturación Recurrente vs Actual", 80, 150, 100) / 100.0

st.sidebar.header("🚀 5. Modelo Inicial (Simulado $ILF+ICLF$)")
ILF_base_param = st.sidebar.number_input("Licencia Base Fija ($ILF_{\\base}$ COP)", value=2500000, step=500000)
target_setup_pequeño = st.sidebar.number_input("Cobro Inicial Target Cliente Pequeño ($)", value=4500000, step=500000)
target_setup_grande = st.sidebar.number_input("Cobro Inicial Target Cliente Grande ($)", value=30000000, step=1000000)

st.sidebar.header("📊 6. Derivados y Retención LTV")
pct_MLF = st.sidebar.slider("% MLF (Mantenimiento)", 1.0, 10.0, 3.0, 0.5) / 100.0
pct_PSF = st.sidebar.slider("% PSF (Soporte)", 5.0, 30.0, 15.0, 1.0) / 100.0
churn_pequeño = st.sidebar.slider("Churn Mensual Pequeños (%)", 0.5, 6.0, 2.5, 0.1) / 100.0
churn_grande = st.sidebar.slider("Churn Mensual Grandes (%)", 0.1, 2.5, 0.5, 0.1) / 100.0
meses_ltv = st.sidebar.slider("Horizonte Evaluación LTV (Meses)", 12, 48, 24, 6)

def calc_bolsa_acum(b_idx, T1, Dmax, k):
    """Calcula las transacciones acumuladas requeridas para alcanzar la bolsa b_idx."""
    val = (T1 * b_idx - k) + np.sqrt((T1 * b_idx - k)**2 + 4 * (1 - Dmax) * k * T1 * b_idx)
    return val / (2 - 2 * Dmax)

def calc_mclf_cliente(vol, P_base, T1, Dmax, k):
    """Calcula el cobro por bolsas transaccionales (MCLF) de un volumen dado."""
    if vol <= 0:
        return 0.0
    b = 1
    acum = calc_bolsa_acum(b, T1, Dmax, k)
    while acum < vol and b < 200:
        b += 1
        acum = calc_bolsa_acum(b, T1, Dmax, k)
    return b * (P_base * T1)

rev_actual_total = df_work["valor cobrado"].sum()
target_rev_rec = rev_actual_total * Rev_target_pct

def loss_recurrente(params):
    P_base, T1 = params
    if P_base <= 0 or T1 <= 1:
        return 1e15
    
    recurrentes_nuevos = []
    for _, row in df_work.iterrows():
        mclf = calc_mclf_cliente(row["# txn"], P_base, T1, D_max, k_sens)
        mlf_psf = ILF_base_param * (pct_MLF + pct_PSF)
        tot = max(MCB_piso, mclf + mlf_psf)
        recurrentes_nuevos.append(tot)
    
    recurrentes_nuevos = np.array(recurrentes_nuevos)
    # Error cuadrático ponderado para amoldar la curva al valor cobrado real
    mse = np.mean((recurrentes_nuevos - df_work["valor cobrado"])**2)
    # Penalización dura si cae por debajo de la meta de ingresos
    rev_penalty = max(0, target_rev_rec - recurrentes_nuevos.sum())**2
    return mse + 5 * rev_penalty

# Optimización por Nelder-Mead
res_rec = opt.minimize(loss_recurrente, x0=[2000.0, 150.0], method='Nelder-Mead')
P_base_MCLF_opt = max(50.0, res_rec.x[0])
T1_opt = max(10.0, res_rec.x[1])

vol_max = max(1, df_work["# txn"].max())
vol_min = max(1, df_work["# txn"].min())

ICLF_target_small = max(0, target_setup_pequeño - ILF_base_param)
ICLF_target_large = max(0, target_setup_grande - ILF_base_param)

# Tarifa base unitaria para alcanzar la meta en el volumen máximo contratado
P_base_ICLF_opt = ICLF_target_large / vol_max

df_res = df_work.copy()

# 1. Recurrente Nuevo
df_res["MCLF_Nuevo"] = df_res["# txn"].apply(lambda v: calc_mclf_cliente(v, P_base_MCLF_opt, T1_opt, D_max, k_sens))
df_res["MLF_PSF"] = ILF_base_param * (pct_MLF + pct_PSF)
df_res["Recurrente_Nuevo"] = np.maximum(MCB_piso, df_res["MCLF_Nuevo"] + df_res["MLF_PSF"])
df_res["Diff_Recurrente"] = df_res["Recurrente_Nuevo"] - df_res["valor cobrado"]
df_res["Var_Pct_Recurrente"] = (df_res["Diff_Recurrente"] / np.maximum(1.0, df_res["valor cobrado"])) * 100.0
df_res["En_Piso_MCB"] = df_res["Recurrente_Nuevo"] == MCB_piso

# 2. Inicial Simulado (Como si fueran clientes nuevos ingresando hoy)
df_res["ILF_Nuevo"] = ILF_base_param
df_res["ICLF_Nuevo"] = df_res["# txn"].apply(lambda v: max(ICLF_target_small, v * P_base_ICLF_opt))
df_res["Inicial_Simulado"] = df_res["ILF_Nuevo"] + df_res["ICLF_Nuevo"]

# 3. Churn y LTV Proyectado
q33 = df_res["# txn"].quantile(0.33)
q66 = df_res["# txn"].quantile(0.66)

def calc_churn(v):
    if v <= q33:
        return churn_pequeño
    elif v >= q66:
        return churn_grande
    else:
        return (churn_pequeño + churn_grande) / 2.0

df_res["Churn_Est"] = df_res["# txn"].apply(calc_churn)
df_res["LTV_Proyectado"] = df_res["Inicial_Simulado"] + (df_res["Recurrente_Nuevo"] / df_res["Churn_Est"]) * (1 - (1 - df_res["Churn_Est"])**meses_ltv)

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("P_base MCLF Calibrado", f"${P_base_MCLF_opt:,.0f} COP")
col2.metric("Bolsa T1 Optimizada", f"{T1_opt:,.0f} Txns")
col3.metric("Facturación Recurrente Actual", f"${rev_actual_total:,.0f} COP")
col4.metric("Facturación Recurrente Nueva", f"${df_res['Recurrente_Nuevo'].sum():,.0f} COP", delta=f"{((df_res['Recurrente_Nuevo'].sum()/rev_actual_total)-1)*100:.1f}%")
col5.metric("Setup Total Simulado (Ingreso)", f"${df_res['Inicial_Simulado'].sum():,.0f} COP")

st.markdown("---")

tab_rec, tab_init, tab_ltv, tab_data = st.tabs([
    "📈 Recurrente: Comparativo Real vs Nuevo",
    "🚀 Inicial: Simulación Cobro Entrada",
    "💎 LTV & Segmentación",
    "📄 Tabla General de Datos"
])

with tab_rec:
    st.subheader("Evaluación Visual del Modelo Recurrente")
    
    col_r1, col_r2 = st.columns([2, 1])
    
    with col_r1:
        fig_rec = go.Figure()
        fig_rec.add_trace(go.Scatter(
            x=df_res["# txn"], y=df_res["valor cobrado"],
            mode='markers', name='Valor Cobrado Actual (Real)',
            marker=dict(color='crimson', size=9, opacity=0.7),
            text=df_res["ID_Cliente"] + " (" + df_res["producto"] + ")"
        ))
        fig_rec.add_trace(go.Scatter(
            x=df_res["# txn"], y=df_res["Recurrente_Nuevo"],
            mode='markers', name='Recurrente Nuevo (Optimizado)',
            marker=dict(color='royalblue', size=11, symbol='diamond'),
            text=df_res["ID_Cliente"]
        ))
        fig_rec.add_hline(y=MCB_piso, line_dash="dash", line_color="orange", annotation_text=f"Piso MCB (${MCB_piso:,.0f})")
        fig_rec.update_layout(
            title="Comparativa: Facturación Actual vs Modelo Nuevo por Volumen",
            xaxis_title="Volumen Transaccional Mensual (# txn) - Escala Log",
            yaxis_title="Cobro Mensual ($ COP)",
            xaxis_type="log",
            height=450
        )
        st.plotly_chart(fig_rec, use_container_width=True)
        
    with col_r2:
        pct_piso = (df_res["En_Piso_MCB"].sum() / len(df_res)) * 100
        st.metric("Clientes que quedan en Piso MCB", f"{df_res['En_Piso_MCB'].sum()} ({pct_piso:.1f}%)")
        
        fig_hist = px.histogram(
            df_res, x="Var_Pct_Recurrente", nbins=20,
            title="Distribución Variación % Cobro Recurrente",
            labels={"Var_Pct_Recurrente": "Variación % vs Actual"},
            color_discrete_sequence=['teal']
        )
        fig_hist.update_layout(height=320)
        st.plotly_chart(fig_hist, use_container_width=True)

with tab_init:
    st.subheader("Evaluación del Cobro Inicial Simulado ($ILF + ICLF$)")
    st.info("💡 Muestra el cobro de entrada que tendría cada cliente según su volumen transaccional actual si ingresara como cliente nuevo.")
    
    col_i1, col_i2 = st.columns([2, 1])
    
    with col_i1:
        # Gráfico apilado de ILF e ICLF por cliente
        fig_init = go.Figure()
        fig_init.add_trace(go.Bar(
            x=df_res["ID_Cliente"], y=df_res["ILF_Nuevo"],
            name="ILF (Licencia Base Fija)", marker_color="darkcyan"
        ))
        fig_init.add_trace(go.Bar(
            x=df_res["ID_Cliente"], y=df_res["ICLF_Nuevo"],
            name="ICLF (Capacidad de Setup)", marker_color="sandybrown"
        ))
        fig_init.update_layout(
            barmode='stack',
            title="Estructura del Cobro de Entrada Simulado por Cliente",
            xaxis_title="Clientes Actuales",
            yaxis_title="Cobro Inicial ($ COP)",
            height=450
        )
        st.plotly_chart(fig_init, use_container_width=True)
        
    with col_i2:
        st.markdown("#### Métricas Descriptivas Inicial")
        st.write(f"**Cobro Inicial Promedio:** ${df_res['Inicial_Simulado'].mean():,.0f} COP")
        st.write(f"**Cobro Mínimo Simulado:** ${df_res['Inicial_Simulado'].min():,.0f} COP")
        st.write(f"**Cobro Máximo Simulado:** ${df_res['Inicial_Simulado'].max():,.0f} COP")
        
        fig_scatter_init = px.scatter(
            df_res, x="# txn", y="Inicial_Simulado", color="producto",
            title="Curva Cobro Inicial vs Volumen",
            log_x=True
        )
        fig_scatter_init.update_layout(height=300)
        st.plotly_chart(fig_scatter_init, use_container_width=True)

with tab_ltv:
    st.subheader("Estimación de LTV Proyectado")
    
    fig_ltv = px.scatter(
        df_res, x="# txn", y="LTV_Proyectado", color="producto", size="Recurrente_Nuevo",
        hover_data=["ID_Cliente", "Inicial_Simulado", "Recurrente_Nuevo"],
        log_x=True, title=f"Proyección de LTV a {meses_ltv} Meses por Cliente"
    )
    fig_ltv.update_layout(height=450)
    st.plotly_chart(fig_ltv, use_container_width=True)

with tab_data:
    st.subheader("Detalle de Cartera y Descarga de Resultados")
    
    display_cols = ["ID_Cliente", "producto", "# txn", "valor cobrado", "Recurrente_Nuevo", "Diff_Recurrente", "Var_Pct_Recurrente", "ILF_Nuevo", "ICLF_Nuevo", "Inicial_Simulado", "LTV_Proyectado"]
    
    df_styled = df_res[display_cols].copy()
    
    st.dataframe(
        df_styled.style.format({
            "valor cobrado": "${:,.0f}",
            "Recurrente_Nuevo": "${:,.0f}",
            "Diff_Recurrente": "${:,.0f}",
            "Var_Pct_Recurrente": "{:+.1f}%",
            "ILF_Nuevo": "${:,.0f}",
            "ICLF_Nuevo": "${:,.0f}",
            "Inicial_Simulado": "${:,.0f}",
            "LTV_Proyectado": "${:,.0f}"
        }),
        use_container_width=True
    )
    
    # Exportar resultados a CSV
    csv_buffer = io.StringIO()
    df_styled.to_csv(csv_buffer, index=False)
    st.download_button(
        label="📥 Descargar Simulación Completa (CSV)",
        data=csv_buffer.getvalue(),
        file_name="simulacion_tarifas_ptesa.csv",
        mime="text/csv"
    )
