import streamlit as st
import numpy as np
import pandas as pd
import scipy.optimize as opt
import plotly.graph_objects as go
import plotly.express as px
import io

st.set_page_config(
    page_title="Modelador Tarifario PTESA - Evaluador por Producto",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    div[data-testid="stMetricValue"] {
        font-size: 1.15rem !important;
        font-weight: 600 !important;
        white-space: nowrap !important;
    }
    div[data-testid="stMetricLabel"] {
        font-size: 0.82rem !important;
    }
    div[data-testid="stMetricDelta"] {
        font-size: 0.80rem !important;
    }
</style>
""", unsafe_allow_html=True)

st.title("⚡ Modelador Tarifario Integrado (Análisis por Producto)")

st.markdown("""
Esta herramienta evalúa el impacto financiero del **nuevo esquema tarifario por bolsas transaccionales** sobre la cartera de clientes.
Para garantizar la consistencia en los volúmenes y la estructura de costos, **el análisis se realiza obligatoriamente producto por producto**.
""")

with st.expander("📖 **¿Cómo funciona la lectura de datos y el modelo de bolsas? (Haz clic para expandir)**", expanded=False):
    st.markdown("""
    ### 🎯 Conceptos Clave del Esquema de Precios:
    1. **Tarifa Base Unitario ($P_{\\text{base}}$):** Precio inicial por transacción individual en la primera bolsa.
    2. **Tamaño Base de Bolsa ($T_1$):** Número de transacciones contenidas en la primera bolsa.
    3. **Valor Fijo por Bolsa:** Cada bolsa adicional cuesta exactamente $P_{\\text{base}} \\times T_1$ COP.
    4. **Ecuación Cuadrática con Descuento ($D_{\\max}, k$):** Aunque el costo por bolsa es constante, la cantidad de transacciones *dentro* de cada bolsa subsecuente aumenta progresivamente. Esto reduce automáticamente el precio promedio por transacción a mayor volumen.
    5. **Estructura Multitemporal:** Si tu archivo incluye columnas de `año` y `mes`, puedes analizar periodos específicos o utilizar el promedio mensual consolidado por cliente.
    """)

def load_and_standardize_data(uploaded_file):
    """Carga y estandariza los datos de Excel/CSV a columnas homogéneas con Año y Mes."""
    if uploaded_file is not None:
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)
    else:
        # Generar dataset sintético demostrativo si no hay archivo
        np.random.seed(42)
        n_clientes = 25
        productos = ["Pasarela Pagos", "Corresponsales", "Billetera Virtual"]
        anios = [2024]
        meses = list(range(1, 7))
        
        rows = []
        for c_idx in range(n_clientes):
            prod = np.random.choice(productos)
            base_txns = np.random.randint(400, 15000)
            base_val = base_txns * np.random.uniform(120, 250) + 900000
            cliente_nombre = f"Empresa Alpha {c_idx+1:02d}"
            
            for anio in anios:
                for mes in meses:
                    noise = np.random.uniform(0.88, 1.12)
                    txns = max(10, int(base_txns * noise))
                    val = base_val * noise
                    rows.append({
                        "cliente": cliente_nombre,
                        "producto": prod,
                        "año": anio,
                        "mes": mes,
                        "# txn": txns,
                        "valor cobrado": val
                    })
        df = pd.DataFrame(rows)

    # Mapeo flexible de columnas
    col_map = {}
    for col in df.columns:
        c_clean = str(col).strip().lower()
        if "client" in c_clean or "nombr" in c_clean or "empresa" in c_clean or "razon" in c_clean:
            col_map[col] = "cliente"
        elif "prod" in c_clean:
            col_map[col] = "producto"
        elif "año" in c_clean or "year" in c_clean or "anio" in c_clean or "aňo" in c_clean:
            col_map[col] = "año"
        elif "mes" in c_clean or "month" in c_clean or "perio" in c_clean:
            col_map[col] = "mes"
        elif "txn" in c_clean or "transacc" in c_clean or "vol" in c_clean:
            col_map[col] = "# txn"
        elif "valor" in c_clean or "cobrad" in c_clean or "factur" in c_clean or "rec" in c_clean:
            col_map[col] = "valor cobrado"

    df = df.rename(columns=col_map)
    
    if "cliente" not in df.columns:
        df["cliente"] = [f"Cliente {i+1:02d}" for i in range(len(df))]
    if "producto" not in df.columns:
        df["producto"] = "General"
    if "año" not in df.columns:
        df["año"] = 2024
    if "mes" not in df.columns:
        df["mes"] = 1
    if "# txn" not in df.columns:
        df["# txn"] = 1000
    if "valor cobrado" not in df.columns:
        df["valor cobrado"] = 1500000.0
        
    df["año"] = pd.to_numeric(df["año"], errors='coerce').fillna(2024).astype(int)
    df["mes"] = pd.to_numeric(df["mes"], errors='coerce').fillna(1).astype(int)
    df["# txn"] = pd.to_numeric(df["# txn"], errors='coerce').fillna(1).astype(int)
    df["valor cobrado"] = pd.to_numeric(df["valor cobrado"], errors='coerce').fillna(0.0)
    df["cliente"] = df["cliente"].astype(str)
    df["producto"] = df["producto"].astype(str)
        
    return df

st.sidebar.header("📁 1. Carga de Datos")
uploaded_file = st.sidebar.file_uploader(
    "Subir archivo (`datos_facturacion.xlsx` / CSV)",
    type=["xlsx", "csv"],
    help="Debe incluir columnas como 'cliente', 'producto', '# txn', 'valor cobrado' y opcionalmente 'año' y 'mes'."
)

df_raw = load_and_standardize_data(uploaded_file)

st.sidebar.header("🎯 2. Selección Obligatoria de Producto")

# Filtro Obligatorio: Se elimina 'TODOS' para obligar análisis específico por línea de negocio
lista_productos = sorted(df_raw["producto"].unique().tolist())
if not lista_productos:
    lista_productos = ["General"]

prod_seleccionado = st.sidebar.selectbox(
    "Línea de Producto a Evaluar",
    lista_productos,
    index=0,
    help="El análisis se realiza de forma independiente por producto para mantener coherencia en las tarifas por bolsa."
)

st.sidebar.caption("🔒 *Análisis restringido exclusivamente a:* **" + str(prod_seleccionado) + "**")

df_filtered_prod = df_raw[df_raw["producto"] == prod_seleccionado].copy()

# Filtros de Año y Mes
anios_disponibles = sorted(df_filtered_prod["año"].unique().tolist())
col_f1, col_f2 = st.sidebar.columns(2)

with col_f1:
    anio_sel = st.selectbox("Año", ["TODOS"] + [str(a) for a in anios_disponibles])
with col_f2:
    if anio_sel != "TODOS":
        meses_disponibles = sorted(df_filtered_prod[df_filtered_prod["año"] == int(anio_sel)]["mes"].unique().tolist())
    else:
        meses_disponibles = sorted(df_filtered_prod["mes"].unique().tolist())
    mes_sel = st.selectbox("Mes", ["TODOS"] + [str(m) for m in meses_disponibles])

# Aplicar filtrado temporal
df_filtered_time = df_filtered_prod.copy()
if anio_sel != "TODOS":
    df_filtered_time = df_filtered_time[df_filtered_time["año"] == int(anio_sel)]
if mes_sel != "TODOS":
    df_filtered_time = df_filtered_time[df_filtered_time["mes"] == int(mes_sel)]

st.sidebar.markdown("---")
eval_mode = st.sidebar.radio(
    "Modo de Evaluación Recurrente",
    ["Promedio Mensual por Cliente", "Detalle Registros Filtrados"],
    help="'Promedio Mensual por Cliente' es el modo recomendado para consolidar el histórico de cada empresa a una tarifa mensual representativa."
)

if eval_mode == "Promedio Mensual por Cliente":
    df_work = df_filtered_time.groupby(["cliente", "producto"]).agg(
        num_meses_historial=("mes", "nunique"),
        txns_mean=("# txn", "mean"),
        valor_cobrado=("valor cobrado", "mean"),
        año=("año", "max"),
        mes=("mes", "max")
    ).reset_index()
    df_work["# txn"] = df_work["txns_mean"].astype(int)
    df_work["valor cobrado"] = df_work["valor_cobrado"]
else:
    df_work = df_filtered_time.copy().reset_index(drop=True)

st.sidebar.header("⚙️ 3. Ajuste del Modelo Recurrente")

with st.sidebar.expander("🛠️ Parámetros Recurrentes ($MCLF + MCB$)", expanded=True):
    Rev_target_pct = st.slider(
        "Meta de Recaudo vs Actual (%)",
        80, 150, 100, 5,
        help="Porcentaje de la facturación actual que se desea proyectar o recuperar."
    ) / 100.0

    MCB_piso = st.number_input(
        "Cobro Mínimo Mensual Garantizado ($MCB_{\\text{piso}}$ COP)",
        value=1000000, step=100000,
        help="Tarifa mínima que pagará cualquier cliente independientemente de si transacciona o no."
    )

    D_max = st.slider(
        "Descuento Máximo por Volumen ($D_{\\max}$)",
        0.05, 0.50, 0.30, 0.05,
        help="Porcentaje máximo de descuento progresivo en volumen."
    )

    k_sens = st.slider(
        "Curvatura de Descuento ($k$)",
        100, 3000, 500, 100,
        help="Controla la velocidad con la que se otorgan las bolsas con mayor capacidad."
    )

st.sidebar.header("🚀 4. Ajuste del Modelo Inicial (Setup)")
with st.sidebar.expander("🛠️ Parámetros de Entrada ($ILF + ICLF$)", expanded=False):
    ILF_base_param = st.number_input(
        "Licencia Base Fija ($ILF_{\\text{base}}$ COP)",
        value=2500000, step=500000,
        help="Cobro único inicial fijo por onboarding y puesta en marcha."
    )
    
    target_setup_pequeño = st.number_input(
        "Setup Target Cliente Pequeño ($ COP)",
        value=4500000, step=500000,
        help="Meta comercial de cobro inicial para clientes de menor tamaño."
    )
    
    target_setup_grande = st.number_input(
        "Setup Target Cliente Grande ($ COP)",
        value=30000000, step=1000000,
        help="Meta comercial de cobro inicial para clientes corporativos."
    )

st.sidebar.header("📊 5. Retención y LTV")
with st.sidebar.expander("🛠️ Retención y Churn", expanded=False):
    pct_MLF = st.slider("% Mantenimiento ($MLF$)", 1.0, 10.0, 3.0, 0.5) / 100.0
    pct_PSF = st.slider("% Soporte ($PSF$)", 5.0, 30.0, 15.0, 1.0) / 100.0
    churn_pequeño = st.slider("Churn Mensual Clientes Pequeños (%)", 0.5, 6.0, 2.5, 0.1) / 100.0
    churn_grande = st.slider("Churn Mensual Clientes Grandes (%)", 0.1, 2.5, 0.5, 0.1) / 100.0
    meses_ltv = st.slider("Horizonte de Análisis LTV (Meses)", 12, 48, 24, 6)

# Funciones del modelo de bolsas cuadráticas
def calc_bolsa_acum(b_idx, T1, Dmax, k):
    """Calcula las transacciones acumuladas alcanzadas hasta la bolsa b_idx."""
    val = (T1 * b_idx - k) + np.sqrt((T1 * b_idx - k)**2 + 4 * (1 - Dmax) * k * T1 * b_idx)
    return val / (2 - 2 * Dmax)

def calc_mclf_cliente(vol, P_base, T1, Dmax, k):
    """Calcula el cobro recurrente por bolsas para un volumen determinado."""
    if vol <= 0:
        return 0.0
    b = 1
    acum = calc_bolsa_acum(b, T1, Dmax, k)
    while acum < vol and b < 200:
        b += 1
        acum = calc_bolsa_acum(b, T1, Dmax, k)
    return b * (P_base * T1)

def calc_num_bolsas(vol, T1, Dmax, k):
    """Calcula el número exacto de bolsas necesarias y la capacidad total alcanzada."""
    if vol <= 0:
        return 0, 0.0
    b = 1
    acum = calc_bolsa_acum(b, T1, Dmax, k)
    while acum < vol and b < 200:
        b += 1
        acum = calc_bolsa_acum(b, T1, Dmax, k)
    return b, acum

rev_actual_total = df_work["valor cobrado"].sum()
target_rev_rec = rev_actual_total * Rev_target_pct

# Optimización automática de P_base y T1 para Recurrente (MCLF)
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
    mse = np.mean((recurrentes_nuevos - df_work["valor cobrado"])**2)
    rev_penalty = max(0, target_rev_rec - recurrentes_nuevos.sum())**2
    return mse + 5 * rev_penalty

res_rec = opt.minimize(loss_recurrente, x0=[500.0, 1000.0], method='Nelder-Mead')
P_base_MCLF_opt = max(10.0, res_rec.x[0])
T1_opt = max(10.0, res_rec.x[1])
costo_bolsa_mclf = P_base_MCLF_opt * T1_opt

vol_max = max(1, df_work["# txn"].max())
ICLF_target_small = max(0, target_setup_pequeño - ILF_base_param)
ICLF_target_large = max(0, target_setup_grande - ILF_base_param)

# Cálculo del modelo de bolsas de Capacidad Inicial (ICLF)
b_max_iclf, _ = calc_num_bolsas(vol_max, T1_opt, D_max, k_sens)
costo_bolsa_ICLF_opt = ICLF_target_large / max(1, b_max_iclf)
P_base_ICLF_opt = costo_bolsa_ICLF_opt / T1_opt if T1_opt > 0 else 0.0

def calc_iclf_cliente(vol, P_base_iclf, T1, Dmax, k):
    """Calcula el cobro por bolsas de capacidad inicial (ICLF)."""
    if vol <= 0:
        return 0.0
    b, _ = calc_num_bolsas(vol, T1, Dmax, k)
    return max(ICLF_target_small, b * (P_base_iclf * T1))

df_res = df_work.copy()

# 1. Calculo Recurrente Nuevo (MCLF)
df_res["MCLF_Nuevo"] = df_res["# txn"].apply(lambda v: calc_mclf_cliente(v, P_base_MCLF_opt, T1_opt, D_max, k_sens))
df_res["MLF_PSF"] = ILF_base_param * (pct_MLF + pct_PSF)
df_res["Recurrente_Nuevo"] = np.maximum(MCB_piso, df_res["MCLF_Nuevo"] + df_res["MLF_PSF"])
df_res["Diff_Recurrente"] = df_res["Recurrente_Nuevo"] - df_res["valor cobrado"]
df_res["Var_Pct_Recurrente"] = (df_res["Diff_Recurrente"] / np.maximum(1.0, df_res["valor cobrado"])) * 100.0
df_res["En_Piso_MCB"] = df_res["Recurrente_Nuevo"] == MCB_piso

# 2. Inicial Simulado por Bolsas (ICLF)
df_res["ILF_Nuevo"] = ILF_base_param
df_res["ICLF_Nuevo"] = df_res["# txn"].apply(lambda v: calc_iclf_cliente(v, P_base_ICLF_opt, T1_opt, D_max, k_sens))
df_res["Inicial_Simulado"] = df_res["ILF_Nuevo"] + df_res["ICLF_Nuevo"]

# 3. LTV Proyectado
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

rev_nueva_total = df_res['Recurrente_Nuevo'].sum()
diff_total = rev_nueva_total - rev_actual_total
pct_variacion_total = (diff_total / max(1.0, rev_actual_total)) * 100.0

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Facturación Actual Evaluada", f"${rev_actual_total:,.0f} COP", help="Suma de facturación del producto seleccionado.")
col2.metric("Facturación Modelo Nuevo", f"${rev_nueva_total:,.0f} COP", delta=f"{pct_variacion_total:+.1f}%", help="Impacto estimado mensual.")
col3.metric("Tarifa Piso Mensual", f"${MCB_piso:,.0f} COP")
col4.metric("% en Tarifa Piso", f"{(df_res['En_Piso_MCB'].sum()/len(df_res))*100:.1f}%")
col5.metric("Setup Total Simulado", f"${df_res['Inicial_Simulado'].sum():,.0f} COP")

st.markdown("---")

tab_exec, tab_time, tab_rec, tab_init, tab_ltv, tab_data = st.tabs([
    "📊 Resumen Ejecutivo",
    "📅 Tendencia Temporal",
    "📈 Recurrente: Real vs Nuevo",
    "🚀 Inicial: Simulación Entradas",
    "💎 LTV & Retención",
    "📄 Inspección Cliente por Cliente"
])

with tab_exec:
    st.subheader(f"📌 Resumen Ejecutivo de Impacto - Producto: {prod_seleccionado}")
    
    st.info(f"""
    💡 **Configuración Activa:** Producto = `{prod_seleccionado}` | Año = `{anio_sel}` | Mes = `{mes_sel}` | Modo = `{eval_mode}`
    """)

    col_e1, col_e2 = st.columns([1.1, 0.9])
    
    with col_e1:
        st.markdown("### 🔍 Estructura de Precios por Bolsas Optimizada")
        st.markdown(f"""
        #### 🔄 1. Modelo Recurrente Mensual ($MCLF + MCB$)
        * **Tarifa Base Recurrente ($P_{{base, MCLF}}$):** `${P_base_MCLF_opt:,.2f} COP/txn`
        * **Capacidad Base de Bolsa ($T_1$):** `{T1_opt:,.0f} transacciones`
        * **Precio Fijo por Bolsa Recurrente:** **`${costo_bolsa_mclf:,.0f} COP`**

        #### 🚀 2. Modelo Inicial / Setup ($ILF + ICLF$)
        * **Licencia Base Fija ($ILF_{{\\text{{base}}}}$):** **`${ILF_base_param:,.0f} COP`** *(Puesta en marcha)*
        * **Tarifa Base Inicial ($P_{{base, ICLF}}$):** `${P_base_ICLF_opt:,.2f} COP/txn`
        * **Precio Fijo por Bolsa de Capacidad Inicial ($ICLF$):** **`${costo_bolsa_ICLF_opt:,.0f} COP`**
        * **Cobro Setup Total Simulado:** Entre `${ILF_base_param + ICLF_target_small:,.0f} COP` y `${ILF_base_param + ICLF_target_large:,.0f} COP` según escala de bolsas.

        👉 **Mecánica del Modelo de Bolsas:**  
        Tanto en el cobro recurrente ($MCLF$) como en el inicial ($ICLF$), la capacidad se vende en **bolsas fijas**. Cada bolsa recurrente cuesta **`${costo_bolsa_mclf:,.0f} COP`** y cada bolsa inicial cuesta **`${costo_bolsa_ICLF_opt:,.0f} COP`**. El número de transacciones contenidas dentro de cada bolsa subsecuente crece progresivamente gracias al descuento cuadrático ($D={D_max:.0%}$).
        """)
        
        if diff_total < 0:
            st.warning("⚠️ **Alerta:** El recaudo proyectado cae por debajo del actual. Ajusta la **Meta de Recaudo** o el **Piso Mínimo**.")
        else:
            st.success("✅ **Resultado Exitoso:** El recaudo cubre o supera la meta fijada para este producto.")

    with col_e2:
        st.markdown("### 📊 Distribución de Ingresos")
        fig_bar_exec = go.Figure(data=[
            go.Bar(name='Facturación Real Actual', x=['Recaudo'], y=[rev_actual_total], marker_color='gray'),
            go.Bar(name='Modelo Nuevo Proyectado', x=['Recaudo'], y=[rev_nueva_total], marker_color='teal')
        ])
        fig_bar_exec.update_layout(
            barmode='group',
            title=f"Comparativa Global de Facturación ({prod_seleccionado})",
            yaxis_title="Monto ($ COP)",
            height=300
        )
        st.plotly_chart(fig_bar_exec, use_container_width=True)

with tab_time:
    st.subheader("📅 Tendencia Histórica de Facturación por Mes")
    
    df_trend = df_filtered_prod.copy()
    df_trend["Periodo"] = df_trend["año"].astype(str) + "-" + df_trend["mes"].apply(lambda m: f"{m:02d}")
    
    df_time_agg = df_trend.groupby("Periodo").agg(
        Total_Txns=("# txn", "sum"),
        Recaudo_Real=("valor cobrado", "sum"),
        Clientes_Activos=("cliente", "nunique")
    ).reset_index().sort_values("Periodo")
    
    recaudo_modelo_hist = []
    for per in df_time_agg["Periodo"]:
        sub = df_trend[df_trend["Periodo"] == per]
        tot_mod = 0
        for _, r in sub.iterrows():
            mclf = calc_mclf_cliente(r["# txn"], P_base_MCLF_opt, T1_opt, D_max, k_sens)
            tot_mod += max(MCB_piso, mclf + ILF_base_param * (pct_MLF + pct_PSF))
        recaudo_modelo_hist.append(tot_mod)
        
    df_time_agg["Recaudo_Modelo"] = recaudo_modelo_hist
    
    fig_time = go.Figure()
    fig_time.add_trace(go.Scatter(
        x=df_time_agg["Periodo"], y=df_time_agg["Recaudo_Real"],
        mode='lines+markers', name='Facturación Real Histórica',
        line=dict(color='gray', width=3)
    ))
    fig_time.add_trace(go.Scatter(
        x=df_time_agg["Periodo"], y=df_time_agg["Recaudo_Modelo"],
        mode='lines+markers', name='Nuevo Modelo Proyectado',
        line=dict(color='teal', width=3, dash='dash')
    ))
    fig_time.update_layout(
        title=f"Evolución Mensual del Recaudo para {prod_seleccionado}",
        xaxis_title="Periodo (Año-Mes)",
        yaxis_title="Recaudo Total ($ COP)",
        height=400
    )
    st.plotly_chart(fig_time, use_container_width=True)

with tab_rec:
    st.subheader("📈 Comparativa Punto a Punto: Facturación Real vs Nuevo Modelo")
    
    col_r1, col_r2 = st.columns([1.8, 1.2])
    
    with col_r1:
        fig_rec = go.Figure()
        fig_rec.add_trace(go.Scatter(
            x=df_res["# txn"], y=df_res["valor cobrado"],
            mode='markers', name='Factura Real Actual',
            marker=dict(color='crimson', size=9, opacity=0.7),
            text=df_res["cliente"],
            hovertemplate="<b>%{text}</b><br>Volumen: %{x:,} txns<br>Cobro Actual: $%{y:,.0f} COP<extra></extra>"
        ))
        fig_rec.add_trace(go.Scatter(
            x=df_res["# txn"], y=df_res["Recurrente_Nuevo"],
            mode='markers', name='Nuevo Modelo (Bolsas)',
            marker=dict(color='royalblue', size=11, symbol='diamond'),
            text=df_res["cliente"],
            hovertemplate="<b>%{text}</b><br>Volumen: %{x:,} txns<br>Cobro Nuevo: $%{y:,.0f} COP<extra></extra>"
        ))
        fig_rec.add_hline(y=MCB_piso, line_dash="dash", line_color="orange", annotation_text=f"Piso Mínimo (${MCB_piso:,.0f})")
        fig_rec.update_layout(
            title=f"Cobro Mensual por Cliente vs Volumen Transaccional ({prod_seleccionado})",
            xaxis_title="Volumen Transaccional Mensual (# txn)",
            yaxis_title="Cobro Mensual ($ COP)",
            xaxis_type="log",
            height=440
        )
        st.plotly_chart(fig_rec, use_container_width=True)
        
    with col_r2:
        st.markdown("#### 📊 Distribución de Variación % vs Actual")
        fig_hist = px.histogram(
            df_res, x="Var_Pct_Recurrente", nbins=15,
            title="Variación % en la Factura del Cliente",
            labels={"Var_Pct_Recurrente": "Variación % vs Factura Actual"},
            color_discrete_sequence=['darkcyan']
        )
        fig_hist.update_layout(height=340)
        st.plotly_chart(fig_hist, use_container_width=True)

    st.markdown("---")
    st.markdown("### 📋 Tabla Escalar de Bolsas Transaccionales (Ecuación Cuadrática con Descuento)")
    st.caption("Esta tabla ilustra cómo cada bolsa adicional cuesta exactamente la misma tarifa fija, pero acomoda progresivamente mayor cantidad de transacciones.")

    # Generación de la tabla de bolsas
    bolsas_list = []
    prev_acum = 0
    for b in range(1, 11):
        acum_txns = calc_bolsa_acum(b, T1_opt, D_max, k_sens)
        txns_en_bolsa = acum_txns - prev_acum
        costo_total = b * costo_bolsa_base
        tarifa_efectiva = costo_total / acum_txns if acum_txns > 0 else 0
        desc_pct = (1 - (tarifa_efectiva / P_base_MCLF_opt)) * 100 if P_base_MCLF_opt > 0 else 0
        
        bolsas_list.append({
            "Bolsa #": f"Bolsa {b}",
            "Costo Fijo por Bolsa": costo_bolsa_base,
            "Costo Acumulado Total": costo_total,
            "Capacidad Txn Acumulada": int(round(acum_txns)),
            "Txns Adicionales en esta Bolsa": int(round(txns_en_bolsa)),
            "Tarifa Promedio ($/txn)": tarifa_efectiva,
            "Descuento Efectivo (%)": max(0.0, desc_pct)
        })
        prev_acum = acum_txns

    df_bolsas_tbl = pd.DataFrame(bolsas_list)
    st.dataframe(
        df_bolsas_tbl.style.format({
            "Costo Fijo por Bolsa": "${:,.0f} COP",
            "Costo Acumulado Total": "${:,.0f} COP",
            "Capacidad Txn Acumulada": "{:,}",
            "Txns Adicionales en esta Bolsa": "{:,}",
            "Tarifa Promedio ($/txn)": "${:,.2f} COP",
            "Descuento Efectivo (%)": "{:.1f}%"
        }),
        use_container_width=True
    )

with tab_init:
    st.subheader("🚀 Cobro Único de Entrada ($ILF + ICLF$) - Simulación de Onboarding")
    
    col_i1, col_i2 = st.columns([2, 1])
    
    with col_i1:
        fig_init = go.Figure()
        fig_init.add_trace(go.Bar(
            x=df_res["cliente"], y=df_res["ILF_Nuevo"],
            name="ILF (Licencia Base Fija)", marker_color="darkslategrey"
        ))
        fig_init.add_trace(go.Bar(
            x=df_res["cliente"], y=df_res["ICLF_Nuevo"],
            name="ICLF (Capacidad de Setup)", marker_color="sandybrown"
        ))
        fig_init.update_layout(
            barmode='stack',
            title=f"Estructura del Cobro Inicial Simulado por Cliente ({prod_seleccionado})",
            xaxis_title="Clientes",
            yaxis_title="Cobro Inicial ($ COP)",
            height=430
        )
        st.plotly_chart(fig_init, use_container_width=True)
        
    with col_i2:
        st.markdown("#### 📋 Métricas del Setup Proyectado")
        st.metric("Setup Promedio por Cliente", f"${df_res['Inicial_Simulado'].mean():,.0f} COP")
        st.metric("Setup Mínimo", f"${df_res['Inicial_Simulado'].min():,.0f} COP")
        st.metric("Setup Máximo", f"${df_res['Inicial_Simulado'].max():,.0f} COP")

with tab_ltv:
    st.subheader("💎 Valor del Cliente en el Tiempo (LTV Proyectado)")
    
    fig_ltv = px.scatter(
        df_res, x="# txn", y="LTV_Proyectado", size="Recurrente_Nuevo",
        hover_name="cliente", hover_data=["cliente", "Inicial_Simulado", "Recurrente_Nuevo"],
        log_x=True, title=f"LTV Proyectado a {meses_ltv} Meses para {prod_seleccionado}",
        color_discrete_sequence=['teal']
    )
    fig_ltv.update_layout(height=430)
    st.plotly_chart(fig_ltv, use_container_width=True)

with tab_data:
    st.subheader("🔍 Inspección Cliente por Cliente y Exportación")
    
    cliente_sel = st.selectbox("Selecciona un cliente para evaluar su impacto individual:", df_res["cliente"].unique())
    row_c = df_res[df_res["cliente"] == cliente_sel].iloc[0]
    
    col_c1, col_c2, col_c3, col_c4, col_c5 = st.columns(5)
    col_c1.metric("Línea de Producto", str(row_c["producto"]))
    col_c2.metric("Volumen Transaccional", f"{row_c['# txn']:,} txns")
    col_c3.metric("Facturación Actual", f"${row_c['valor cobrado']:,.0f} COP")
    col_c4.metric("Facturación Recurrente Nueva", f"${row_c['Recurrente_Nuevo']:,.0f} COP", delta=f"{row_c['Var_Pct_Recurrente']:+.1f}%")
    col_c5.metric("Setup Inicial Simulado", f"${row_c['Inicial_Simulado']:,.0f} COP")
    
    st.markdown("---")
    st.markdown(f"### 📦 Desglose Tarifario Detallado de Bolsas para **{row_c['cliente']}**")
    
    vol_c = row_c["# txn"]
    
    # Calcular bolsas requeridas para el cliente tanto en MCLF como en ICLF
    b_c_mclf, acum_c_mclf = calc_num_bolsas(vol_c, T1_opt, D_max, k_sens)
    b_c_iclf, acum_c_iclf = calc_num_bolsas(vol_c, T1_opt, D_max, k_sens)
        
    mclf_c = row_c["MCLF_Nuevo"]
    ilf_c = row_c["ILF_Nuevo"]
    iclf_c = row_c["ICLF_Nuevo"]
    setup_tot_c = row_c["Inicial_Simulado"]
    rec_tot_c = row_c["Recurrente_Nuevo"]
    
    col_detail1, col_detail2 = st.columns(2)
    
    with col_detail1:
        st.markdown("#### 🔄 Bolsas Recurrentes Mensuales ($MCLF + MCB$)")
        st.markdown(f"""
        * **Bolsas Recurrentes Requeridas:** `{b_c_mclf} bolsa(s)` (Capacidad total: {acum_c_mclf:,.0f} txns)
        * **Precio Fijo por Bolsa Recurrente:** `${costo_bolsa_mclf:,.0f} COP` (${P_base_MCLF_opt:,.2f}/txn)
        * **Subtotal Bolsas Recurrentes ($MCLF$):** `${mclf_c:,.0f} COP`
        * **Mantenimiento & Soporte ($MLF+PSF$):** `${row_c['MLF_PSF']:,.0f} COP`
        * **Cobro Recurrente Total Aplicado:** **`${rec_tot_c:,.0f} COP`** `{"(Aplica Tarifa Mínima MCB)" if row_c["En_Piso_MCB"] else ""}`
        """)
        
    with col_detail2:
        st.markdown("#### 🚀 Bolsas de Capacidad Inicial ($ILF + ICLF$)")
        st.markdown(f"""
        * **Bolsas Iniciales Requeridas:** `{b_c_iclf} bolsa(s)` (Capacidad total: {acum_c_iclf:,.0f} txns)
        * **Precio Fijo por Bolsa Inicial ($ICLF$):** `${costo_bolsa_ICLF_opt:,.0f} COP` (${P_base_ICLF_opt:,.2f}/txn)
        * **Subtotal Capacidad Inicial ($ICLF$):** `${iclf_c:,.0f} COP`
        * **Licencia Base Fija ($ILF$):** `${ilf_c:,.0f} COP`
        * **Cobro Único de Entrada Total:** **`${setup_tot_c:,.0f} COP`**
        * **LTV Proyectado a {meses_ltv} Meses:** `${row_c['LTV_Proyectado']:,.0f} COP`
        """)

    st.markdown(f"#### 📊 Tabla de Estructura de Bolsas Aplicada a **{row_c['cliente']}** ({vol_c:,} txns)")
    
    client_bolsas_list = []
    prev_a = 0
    for b in range(1, b_c_mclf + 1):
        acum_t = calc_bolsa_acum(b, T1_opt, D_max, k_sens)
        txns_b = acum_t - prev_a
        c_mclf_total = b * costo_bolsa_mclf
        c_iclf_total = b * costo_bolsa_ICLF_opt
        tar_ef_mclf = c_mclf_total / acum_t if acum_t > 0 else 0
        desc_p = (1 - (tar_ef_mclf / P_base_MCLF_opt)) * 100 if P_base_MCLF_opt > 0 else 0
        es_bolsa_final = (b == b_c_mclf)
        
        client_bolsas_list.append({
            "Bolsa #": f"Bolsa {b}" + (" (Capacidad Alcanzada)" if es_bolsa_final else ""),
            "Capacidad Txn Acumulada": int(round(acum_t)),
            "Txns Adicionales en Bolsa": int(round(txns_b)),
            "Costo Bolsa Recurrente (MCLF)": costo_bolsa_mclf,
            "Costo Acumulado MCLF": c_mclf_total,
            "Costo Bolsa Inicial (ICLF)": costo_bolsa_ICLF_opt,
            "Costo Acumulado ICLF": c_iclf_total,
            "Tarifa Recurrente Promedio ($/txn)": tar_ef_mclf,
            "Descuento Efectivo (%)": max(0.0, desc_p)
        })
        prev_a = acum_t

    df_client_bolsas = pd.DataFrame(client_bolsas_list)
    st.dataframe(
        df_client_bolsas.style.format({
            "Capacidad Txn Acumulada": "{:,}",
            "Txns Adicionales en Bolsa": "{:,}",
            "Costo Bolsa Recurrente (MCLF)": "${:,.0f} COP",
            "Costo Acumulado MCLF": "${:,.0f} COP",
            "Costo Bolsa Inicial (ICLF)": "${:,.0f} COP",
            "Costo Acumulado ICLF": "${:,.0f} COP",
            "Tarifa Recurrente Promedio ($/txn)": "${:,.2f} COP",
            "Descuento Efectivo (%)": "{:.1f}%"
        }),
        use_container_width=True
    )

    st.markdown("---")
    st.markdown("### 📄 Tabla de Cartera y Resultados de Simulación")
    
    cols_base = ["cliente", "producto", "año", "mes", "# txn", "valor cobrado", "Recurrente_Nuevo", "Diff_Recurrente", "Var_Pct_Recurrente", "Inicial_Simulado", "LTV_Proyectado"]
    display_cols = [c for c in cols_base if c in df_res.columns]
    
    df_styled = df_res[display_cols].copy()
    
    st.dataframe(
        df_styled.style.format({
            "# txn": "{:,}",
            "valor cobrado": "${:,.0f} COP",
            "Recurrente_Nuevo": "${:,.0f} COP",
            "Diff_Recurrente": "${:,.0f} COP",
            "Var_Pct_Recurrente": "{:+.1f}%",
            "Inicial_Simulado": "${:,.0f} COP",
            "LTV_Proyectado": "${:,.0f} COP"
        }),
        use_container_width=True
    )
    
    csv_buffer = io.StringIO()
    df_styled.to_csv(csv_buffer, index=False)
    st.download_button(
        label="📥 Descargar Simulación Completa (CSV)",
        data=csv_buffer.getvalue(),
        file_name=f"simulacion_tarifaria_{prod_seleccionado}_{anio_sel}_{mes_sel}.csv",
        mime="text/csv"
    )
