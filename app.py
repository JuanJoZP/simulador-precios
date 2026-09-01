import streamlit as st
import numpy as np
import pandas as pd
import scipy.optimize as opt
import plotly.graph_objects as go
import plotly.express as px
import io

st.set_page_config(
    page_title="Modelador Tarifario PTESA - Evaluador de Impacto",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("⚡ Modelador Tarifario Integrado (Recurrente e Inicial)")

st.markdown("""
Esta herramienta permite **simular y evaluar el impacto del nuevo esquema tarifario** sobre la cartera de clientes actual.
Está diseñada para proyectar ingresos, ajustar parámetros de cobro en tiempo real y comparar los valores cobrados hoy contra la propuesta tarifaria.
""")

with st.expander("📖 **¿Cómo funciona este modelador y qué significa cada concepto? (Haz clic para expandir)**", expanded=False):
    st.markdown("""
    ### 🎯 Objetivos de la herramienta:
    1. **Evaluar el Cobro Recurrente (Mensual):** Compara lo que le cobras hoy a cada cliente (`valor cobrado`) contra lo que pagaría en el nuevo esquema basado en bolsas transaccionales ($MCLF$) + piso mínimo garantizado ($MCB$).
    2. **Simular el Cobro Inicial (Setup / Entradas):** Calcula el valor de entrada ($ILF + ICLF$) que le correspondería pagar a tu cartera actual si fueran contratados hoy como clientes nuevos con su volumen actual.

    ---
    ### 💡 Conceptos Clave en Lenguaje Comercial:
    * **Cobro Recurrente Mensual:** Lo que el cliente paga cada mes. Se compone de:
      * **Bolsa Transaccional ($MCLF$):** Paquetes de volumen transaccional ($T_1$) con descuento progresivo por escala.
      * **Soporte y Mantenimiento ($MLF + PSF$):** Porcentaje mensual derivado de la licencia base.
      * **Piso Mínimo Mensual ($MCB_{\\text{piso}}$):** Tarifa mínima obligatoria. Si la suma del consumo del cliente no alcanza este valor, el cliente paga la tarifa piso.
    * **Cobro Inicial / Setup (Pago Único al Entrar):**
      * **Licencia Base ($ILF_{\\text{base}}$):** Derecho de uso base y puesta en marcha inicial (monto fijo).
      * **Cargo por Capacidad ($ICLF$):** Cobro proporcional a la capacidad operativa/volumen estimado con el que inicia el cliente.
    """)

def load_and_standardize_data(uploaded_file):
    """Carga y estandariza los datos de Excel/CSV a columnas homogéneas."""
    if uploaded_file is not None:
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)
    else:
        # Generar dataset sintético demostrativo si no hay archivo subido
        np.random.seed(42)
        n = 45
        productos = np.random.choice(["Pasarela Pagos", "Corresponsales", "Billetera Virtual"], size=n)
        txns = np.random.lognormal(mean=7.5, sigma=1.2, size=n).astype(int) + 100
        valores = txns * np.random.uniform(1200, 2400, size=n) + 800000
        df = pd.DataFrame({
            "cliente": [f"Empresa Alpha {i+1:02d}" for i in range(n)],
            "producto": productos,
            "# txn": txns,
            "valor cobrado": valores
        })

    # Mapeo flexible de columnas para evitar errores de tipografía
    col_map = {}
    for col in df.columns:
        c_clean = str(col).strip().lower()
        if "client" in c_clean or "nombr" in c_clean or "empresa" in c_clean or "razon" in c_clean:
            col_map[col] = "cliente"
        elif "prod" in c_clean:
            col_map[col] = "producto"
        elif "txn" in c_clean or "transacc" in c_clean or "vol" in c_clean:
            col_map[col] = "# txn"
        elif "valor" in c_clean or "cobrad" in c_clean or "factur" in c_clean or "rec" in c_clean:
            col_map[col] = "valor cobrado"

    df = df.rename(columns=col_map)
    
    if "cliente" not in df.columns:
        if "ID_Cliente" in df.columns:
            df["cliente"] = df["ID_Cliente"]
        else:
            df["cliente"] = [f"Cliente {i+1:02d}" for i in range(len(df))]
            
    if "producto" not in df.columns:
        df["producto"] = "General"
    if "# txn" not in df.columns:
        df["# txn"] = 1000
    if "valor cobrado" not in df.columns:
        df["valor cobrado"] = 1500000.0
        
    df["# txn"] = pd.to_numeric(df["# txn"], errors='coerce').fillna(1).astype(int)
    df["valor cobrado"] = pd.to_numeric(df["valor cobrado"], errors='coerce').fillna(0.0)
    df["cliente"] = df["cliente"].astype(str)
        
    return df

st.sidebar.header("📁 1. Carga de Datos")
uploaded_file = st.sidebar.file_uploader(
    "Subir archivo (`producto_volumen_facturado.xlsx` / CSV)",
    type=["xlsx", "csv"],
    help="El archivo puede contener las columnas: 'cliente', 'producto', '# txn' y 'valor cobrado'."
)

    # Mapeo flexible de columnas para evitar errores de tipografía
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
    
    if "producto" not in df.columns:
        df["producto"] = "General"
    if "# txn" not in df.columns:
        df["# txn"] = 1000
    if "valor cobrado" not in df.columns:
        df["valor cobrado"] = 1500000.0
        
    df["# txn"] = pd.to_numeric(df["# txn"], errors='coerce').fillna(1).astype(int)
    df["valor cobrado"] = pd.to_numeric(df["valor cobrado"], errors='coerce').fillna(0.0)
    
    # Asignar identificador único de cliente si no viene en el archivo
    if "ID_Cliente" not in df.columns:
        df["ID_Cliente"] = [f"Cliente_{i+1:02d}" for i in range(len(df))]
        
    return df

st.sidebar.header("📁 1. Carga de Datos")
uploaded_file = st.sidebar.file_uploader(
    "Subir archivo (`producto_volumen_facturado.xlsx` / CSV)",
    type=["xlsx", "csv"],
    help="El archivo debe tener las columnas: 'producto', '# txn', y 'valor cobrado'."
)

df_raw = load_and_standardize_data(uploaded_file)

st.sidebar.header("🎯 2. Filtro de Análisis")
lista_productos = ["TODOS LOS PRODUCTOS"] + sorted(df_raw["producto"].unique().tolist())
prod_seleccionado = st.sidebar.selectbox(
    "Filtrar por Línea de Producto",
    lista_productos,
    help="Evalúa el comportamiento tarifario de toda la empresa o concéntrate en una línea específica."
)

if prod_seleccionado != "TODOS LOS PRODUCTOS":
    df_work = df_raw[df_raw["producto"] == prod_seleccionado].copy().reset_index(drop=True)
else:
    df_work = df_raw.copy().reset_index(drop=True)

st.sidebar.markdown("---")
st.sidebar.header("⚙️ 3. Ajuste del Modelo Recurrente")

with st.sidebar.expander("🛠️ Parámetros Recurrentes ($MCLF + MCB$)", expanded=True):
    Rev_target_pct = st.slider(
        "Meta de Recaudo vs Actual (%)",
        80, 150, 100, 5,
        help="Define qué porcentaje de la facturación actual esperas recuperar o incrementar con el nuevo modelo."
    ) / 100.0

    MCB_piso = st.number_input(
        "Cobro Mínimo Mensual ($MCB_{\\text{piso}}$ COP)",
        value=1000000, step=100000,
        help="Tarifa mínima garantizada por cliente. Si el consumo calculado es menor a este piso, se cobra este valor."
    )

    D_max = st.slider(
        "Descuento Máximo por Volumen ($D_{\\max}$)",
        0.05, 0.50, 0.30, 0.05,
        help="Porcentaje máximo de descuento progresivo que pueden alcanzar las bolsas de mayor escala."
    )

    k_sens = st.slider(
        "Curvatura de Descuento ($k$)",
        100, 3000, 500, 100,
        help="Controla qué tan rápido se otorga el descuento a medida que aumentan las bolsas de volumen."
    )

st.sidebar.header("🚀 4. Ajuste del Modelo Inicial (Setup)")
with st.sidebar.expander("🛠️ Parámetros de Entrada ($ILF + ICLF$)", expanded=False):
    ILF_base_param = st.number_input(
        "Licencia Base Fija ($ILF_{\\text{base}}$ COP)",
        value=2500000, step=500000,
        help="Cobro fijo inicial para cualquier cliente por concepto de onboarding y setup básico."
    )
    
    target_setup_pequeño = st.number_input(
        "Setup Target Cliente Pequeño ($ COP)",
        value=4500000, step=500000,
        help="Meta comercial de cobro inicial para clientes en el rango mínimo de volumen."
    )
    
    target_setup_grande = st.number_input(
        "Setup Target Cliente Grande ($ COP)",
        value=30000000, step=1000000,
        help="Meta comercial de cobro inicial proyectado para clientes con el volumen más alto registrado."
    )

st.sidebar.header("📊 5. Retención y LTV")
with st.sidebar.expander("🛠️ Retención y Churn", expanded=False):
    pct_MLF = st.slider("% Mantenimiento ($MLF$)", 1.0, 10.0, 3.0, 0.5, help="Mantenimiento mensual derivado de la licencia base.") / 100.0
    pct_PSF = st.slider("% Soporte ($PSF$)", 5.0, 30.0, 15.0, 1.0, help="Soporte mensual derivado de la licencia base.") / 100.0
    churn_pequeño = st.slider("Churn Mensual Clientes Pequeños (%)", 0.5, 6.0, 2.5, 0.1, help="Tasa mensual estimada de cancelación para menor volumen.") / 100.0
    churn_grande = st.slider("Churn Mensual Clientes Grandes (%)", 0.1, 2.5, 0.5, 0.1, help="Tasa mensual estimada de cancelación para corporativos.") / 100.0
    meses_ltv = st.slider("Horizonte de Análisis LTV (Meses)", 12, 48, 24, 6, help="Meses proyectados para evaluar el valor del cliente en el tiempo.")

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

# Algoritmo de calibración automática de P_base y T1 según los knobs activados
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

res_rec = opt.minimize(loss_recurrente, x0=[2000.0, 150.0], method='Nelder-Mead')
P_base_MCLF_opt = max(50.0, res_rec.x[0])
T1_opt = max(10.0, res_rec.x[1])

vol_max = max(1, df_work["# txn"].max())
vol_min = max(1, df_work["# txn"].min())

ICLF_target_small = max(0, target_setup_pequeño - ILF_base_param)
ICLF_target_large = max(0, target_setup_grande - ILF_base_param)
P_base_ICLF_opt = ICLF_target_large / vol_max

df_res = df_work.copy()

# 1. Recurrente Nuevo
df_res["MCLF_Nuevo"] = df_res["# txn"].apply(lambda v: calc_mclf_cliente(v, P_base_MCLF_opt, T1_opt, D_max, k_sens))
df_res["MLF_PSF"] = ILF_base_param * (pct_MLF + pct_PSF)
df_res["Recurrente_Nuevo"] = np.maximum(MCB_piso, df_res["MCLF_Nuevo"] + df_res["MLF_PSF"])
df_res["Diff_Recurrente"] = df_res["Recurrente_Nuevo"] - df_res["valor cobrado"]
df_res["Var_Pct_Recurrente"] = (df_res["Diff_Recurrente"] / np.maximum(1.0, df_res["valor cobrado"])) * 100.0
df_res["En_Piso_MCB"] = df_res["Recurrente_Nuevo"] == MCB_piso

# 2. Inicial Simulado (Como si entraran hoy como clientes nuevos)
df_res["ILF_Nuevo"] = ILF_base_param
df_res["ICLF_Nuevo"] = df_res["# txn"].apply(lambda v: max(ICLF_target_small, v * P_base_ICLF_opt))
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
col1.metric("Facturación Actual", f"${rev_actual_total:,.0f} COP", help="Suma de la facturación mensual actual de la cartera analizada.")
col2.metric("Facturación Modelo Nuevo", f"${rev_nueva_total:,.0f} COP", delta=f"{pct_variacion_total:+.1f}%", help="Impacto total estimado en la facturación mensual al aplicar los nuevos knobs.")
col3.metric("Tarifa Piso Mensual", f"${MCB_piso:,.0f} COP", help="Piso mínimo configurado en la barra lateral.")
col4.metric("% en Tarifa Piso", f"{(df_res['En_Piso_MCB'].sum()/len(df_res))*100:.1f}%", help="Porcentaje de clientes cuyo consumo está por debajo del piso mínimo.")
col5.metric("Setup Total Simulado", f"${df_res['Inicial_Simulado'].sum():,.0f} COP", help="Recaudo único inicial si toda esta cartera contratara hoy de cero.")

st.markdown("---")

tab_exec, tab_rec, tab_init, tab_ltv, tab_data = st.tabs([
    "📊 Resumen Ejecutivo",
    "📈 Recurrente: Real vs Nuevo",
    "🚀 Inicial: Simulación Entradas",
    "💎 LTV & Retención",
    "📄 Inspección Cliente por Cliente"
])

with tab_exec:
    st.subheader("📌 Evaluador Rápido de Impacto Financiero")
    
    st.info("""
    💡 **¿Cómo interpretar esta vista estratégica?**  
    Aquí ves la comparativa global entre lo que recauda la empresa HOY vs. lo que recaudaría aplicando la NUEVA estructura tarifaria.
    * **Recurrente:** Compara directamente el valor histórico mensual cobrado vs el cobro simulado por bolsas transaccionales y tarifa piso.
    * **Iniciales (Setup):** Muestra el recaudo proyectado de tarifa de entrada si esta cartera actual fuera a ingresar hoy como clientes nuevos.
    """)

    col_e1, col_e2 = st.columns([1, 1])
    
    with col_e1:
        st.markdown("### 🔍 Hallazgos Principales")
        st.markdown(f"""
        * **Facturación Recurrente Actual (Real):** `${rev_actual_total:,.0f} COP/mes`
        * **Facturación Proyectada Nuevo Modelo:** `${rev_nueva_total:,.0f} COP/mes`
        * **Diferencia Neta en Recaudo:** `${diff_total:,.0f} COP/mes` ({pct_variacion_total:+.1f}%)
        * **Clientes Protegidos por Piso Mínimo ($MCB$):** `{df_res['En_Piso_MCB'].sum()}` de `{len(df_res)}` clientes ({(df_res['En_Piso_MCB'].sum()/len(df_res))*100:.1f}%)
        * **Tarifa Base Eficiente Calculada ($P_{{base}}$):** `${P_base_MCLF_opt:,.0f} COP` por paquete base de `{T1_opt:,.0f}` transacciones.
        """)
        
        if diff_total < 0:
            st.warning("⚠️ **Atención:** El modelo parametrizado recauda MENOS que la facturación actual. Si deseas cubrir la facturación actual, aumenta la **Meta de Recaudo** o el **Piso Mínimo Mensual** en la barra lateral.")
        else:
            st.success("✅ **Modelo Alineado:** El recaudo proyectado cumple o supera la facturación histórica actual.")

    with col_e2:
        df_prod_summary = df_res.groupby("producto").agg(
            Clientes=("cliente", "count"),
            Recaudo_Actual=("valor cobrado", "sum"),
            Recaudo_Nuevo=("Recurrente_Nuevo", "sum")
        ).reset_index()
        df_prod_summary["Variación %"] = ((df_prod_summary["Recaudo_Nuevo"] - df_prod_summary["Recaudo_Actual"]) / df_prod_summary["Recaudo_Actual"]) * 100
        
        fig_bar_prod = px.bar(
            df_prod_summary, x="producto", y=["Recaudo_Actual", "Recaudo_Nuevo"],
            barmode="group", title="Recaudo Mensual: Actual vs Nuevo por Producto",
            labels={"value": "Monto ($ COP)", "variable": "Esquema Tarifario", "producto": "Línea de Producto"},
            color_discrete_map={"Recaudo_Actual": "gray", "Recaudo_Nuevo": "teal"}
        )
        fig_bar_prod.update_layout(height=320)
        st.plotly_chart(fig_bar_prod, use_container_width=True)

with tab_rec:
    st.subheader("📈 Comparativa Punto a Punto: Facturación Real vs Nuevo Modelo")
    
    st.warning("""
    🔍 **¿Cómo evaluar los cambios visualmente al mover los controles (Knobs)?**
    * **Puntos Rojos (●):** Factura real pagada actualmente por cada **Cliente**.
    * **Diamantes Azules (◆):** Factura que pagaría ese mismo **Cliente** con el nuevo modelo.
    * **Línea Punteada Naranja (--):** Piso mínimo obligatorio ($MCB_{\\text{piso}}$). Todos los clientes abajo de esta línea pagan al menos este valor.
    * *Si mueves el slider de **Meta de Recaudo** o **Piso Mínimo**, observa cómo suben o bajan los diamantes azules respecto a los puntos rojos.*
    """)
    
    col_r1, col_r2 = st.columns([2, 1])
    
    with col_r1:
        fig_rec = go.Figure()
        fig_rec.add_trace(go.Scatter(
            x=df_res["# txn"], y=df_res["valor cobrado"],
            mode='markers', name='Cobrado Actual (Real)',
            marker=dict(color='crimson', size=9, opacity=0.7),
            text=df_res["cliente"] + " (" + df_res["producto"] + ")",
            hovertemplate="<b>%{text}</b><br>Volumen: %{x:,} txns<br>Cobro Actual: $%{y:,.0f} COP<extra></extra>"
        ))
        fig_rec.add_trace(go.Scatter(
            x=df_res["# txn"], y=df_res["Recurrente_Nuevo"],
            mode='markers', name='Nuevo Modelo (Proyectado)',
            marker=dict(color='royalblue', size=11, symbol='diamond'),
            text=df_res["cliente"],
            hovertemplate="<b>%{text}</b><br>Volumen: %{x:,} txns<br>Cobro Nuevo: $%{y:,.0f} COP<extra></extra>"
        ))
        fig_rec.add_hline(y=MCB_piso, line_dash="dash", line_color="orange", annotation_text=f"Piso Mínimo (${MCB_piso:,.0f})")
        fig_rec.update_layout(
            title="Facturación Mensual por Cliente según Volumen Transaccional",
            xaxis_title="Volumen Transaccional Mensual (# txn)",
            yaxis_title="Cobro Mensual ($ COP)",
            xaxis_type="log",
            height=460
        )
        st.plotly_chart(fig_rec, use_container_width=True)
        
    with col_r2:
        st.markdown("#### 📊 Variación Porcentual del Cobro")
        st.write("Muestra qué porcentaje sube o baja la factura para cada cliente.")
        
        fig_hist = px.histogram(
            df_res, x="Var_Pct_Recurrente", nbins=18,
            title="Distribución de Variación % vs Actual",
            labels={"Var_Pct_Recurrente": "Variación % vs Factura Actual"},
            color_discrete_sequence=['darkcyan']
        )
        fig_hist.update_layout(height=340)
        st.plotly_chart(fig_hist, use_container_width=True)

with tab_init:
    st.subheader("🚀 Cobro Único de Entrada ($ILF + ICLF$) - Simulación de Nuevos Ingresos")
    
    st.info("""
    💡 **¿Qué muestra esta sección? (Sin comparación histórica)**  
    Muestra descriptivamente **cuánto se le cobraría a cada cliente actual de entrada** si fueran contratados hoy de cero.
    * **ILF (Gris Oscuro):** Licencia Fija de entrada (Setup / Onboarding).
    * **ICLF (Naranja):** Cargo proporcional a la Capacidad / Volumen transaccional estimado.
    """)
    
    col_i1, col_i2 = st.columns([2, 1])
    
    with col_i1:
        fig_init = go.Figure()
        fig_init.add_trace(go.Bar(
            x=df_res["cliente"], y=df_res["ILF_Nuevo"],
            name="ILF (Licencia Base Fija)", marker_color="darkslategrey",
            hovertemplate="<b>%{x}</b><br>ILF Base: $%{y:,.0f} COP<extra></extra>"
        ))
        fig_init.add_trace(go.Bar(
            x=df_res["cliente"], y=df_res["ICLF_Nuevo"],
            name="ICLF (Capacidad de Setup)", marker_color="sandybrown",
            hovertemplate="<b>%{x}</b><br>ICLF Capacidad: $%{y:,.0f} COP<extra></extra>"
        ))
        fig_init.update_layout(
            barmode='stack',
            title="Estructura del Cobro Único Inicial por Cliente",
            xaxis_title="Clientes Actuales",
            yaxis_title="Cobro Inicial ($ COP)",
            height=450
        )
        st.plotly_chart(fig_init, use_container_width=True)
        
    with col_i2:
        st.markdown("#### 📋 Resumen Descriptivo del Setup")
        st.metric("Cobro Inicial Promedio", f"${df_res['Inicial_Simulado'].mean():,.0f} COP")
        st.metric("Cobro Inicial Mínimo", f"${df_res['Inicial_Simulado'].min():,.0f} COP")
        st.metric("Cobro Inicial Máximo", f"${df_res['Inicial_Simulado'].max():,.0f} COP")
        
        fig_scatter_init = px.scatter(
            df_res, x="# txn", y="Inicial_Simulado", color="producto", hover_name="cliente",
            title="Cobro Inicial vs Volumen Transaccional",
            log_x=True
        )
        fig_scatter_init.update_layout(height=260)
        st.plotly_chart(fig_scatter_init, use_container_width=True)

with tab_ltv:
    st.subheader("💎 Valor del Cliente en el Tiempo (LTV Proyectado)")
    
    st.info(f"""
    💡 **¿Qué es el LTV (Lifetime Value)?**  
    Es el ingreso total proyectado que genera cada **Cliente** sumando el **Cobro Inicial ($ILF+ICLF$)** y su **Cobro Recurrente Mensual** 
    a `{meses_ltv} meses`, descontando la tasa de cancelación (Churn) configurada.
    """)
    
    fig_ltv = px.scatter(
        df_res, x="# txn", y="LTV_Proyectado", color="producto", size="Recurrente_Nuevo",
        hover_name="cliente", hover_data=["cliente", "Inicial_Simulado", "Recurrente_Nuevo"],
        log_x=True, title=f"LTV Proyectado a {meses_ltv} Meses por Cliente (Tamaño = Cobro Recurrente Mensual)"
    )
    fig_ltv.update_layout(height=450)
    st.plotly_chart(fig_ltv, use_container_width=True)

with tab_data:
    st.subheader("🔍 Inspector por Cliente y Exportación de Datos")
    
    st.markdown("### 👤 Inspeccionar un Cliente Específico")
    cliente_sel = st.selectbox("Selecciona un cliente para evaluar su impacto individual:", df_res["cliente"].unique())
    
    row_c = df_res[df_res["cliente"] == cliente_sel].iloc[0]
    
    col_c1, col_c2, col_c3, col_c4 = st.columns(4)
    col_c1.metric("Línea de Producto", str(row_c["producto"]))
    col_c2.metric("Volumen Transaccional", f"{row_c['# txn']:,} txns")
    col_c3.metric("Facturación Actual", f"${row_c['valor cobrado']:,.0f} COP")
    col_c4.metric("Facturación Nueva", f"${row_c['Recurrente_Nuevo']:,.0f} COP", delta=f"{row_c['Var_Pct_Recurrente']:+.1f}%")
    
    with st.expander(f"📌 Desglose Detallado del Cliente: {row_c['cliente']}", expanded=True):
        st.markdown(f"""
        * **Cliente:** `{row_c['cliente']}`
        * **Cobro Recurrente Nuevo:** `${row_c['Recurrente_Nuevo']:,.0f} COP/mes`
          * *Bolsas Transaccionales ($MCLF$):* `${row_c['MCLF_Nuevo']:,.0f} COP`
          * *Mantenimiento y Soporte ($MLF+PSF$):* `${row_c['MLF_PSF']:,.0f} COP`
          * *¿Entró en Tarifa Piso ($MCB$)?* `{"SÍ (Ajustado a Tarifa Mínima)" if row_c["En_Piso_MCB"] else "NO (Pagando por Consumo/Bolsa)"}`
        * **Cobro Inicial Simulado ($Setup$):** `${row_c['Inicial_Simulado']:,.0f} COP`
          * *Licencia Base Fija ($ILF$):* `${row_c['ILF_Nuevo']:,.0f} COP`
          * *Capacidad ($ICLF$):* `${row_c['ICLF_Nuevo']:,.0f} COP`
        * **LTV Proyectado ({meses_ltv} meses):** `${row_c['LTV_Proyectado']:,.0f} COP`
        """)

    st.markdown("---")
    st.markdown("### 📄 Tabla Completa de Cartera y Simulación")
    
    display_cols = ["cliente", "producto", "# txn", "valor cobrado", "Recurrente_Nuevo", "Diff_Recurrente", "Var_Pct_Recurrente", "ILF_Nuevo", "ICLF_Nuevo", "Inicial_Simulado", "LTV_Proyectado"]
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
    
    csv_buffer = io.StringIO()
    df_styled.to_csv(csv_buffer, index=False)
    st.download_button(
        label="📥 Descargar Simulación Completa (CSV)",
        data=csv_buffer.getvalue(),
        file_name="simulacion_tarifas_clientes_ptesa.csv",
        mime="text/csv"
    )
