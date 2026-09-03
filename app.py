import streamlit as st
import numpy as np
import pandas as pd
import scipy.optimize as opt
import plotly.graph_objects as go
import plotly.express as px
import io

st.set_page_config(
    page_title="Modelador Tarifario PTESA - Evaluador por Producto",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for clean layout and non-truncated metrics
st.markdown("""
<style>
    div[data-testid="stMetricValue"] {
        font-size: 1.10rem !important;
        font-weight: 600 !important;
        white-space: normal !important;
        word-wrap: break-word !important;
        overflow: visible !important;
    }
    div[data-testid="stMetricLabel"] {
        font-size: 0.82rem !important;
    }
    div[data-testid="stMetricDelta"] {
        font-size: 0.80rem !important;
    }
</style>
""", unsafe_allow_html=True)

st.title("Simulador de modelo de precios")

st.markdown("""
Esta herramienta simula el impacto financiero del nuevo modelo de precio por bolsas transaccionales sobre los clientes actuales.
El analisis se realiza por producto. Debe cargar el archivo con los datos de transacciones para que funcione (preguntar Juan Jose).
""")

with st.expander("Como funciona la lectura de datos y el modelo de bolsas", expanded=False):
    st.markdown("""
    * **Tarifa Base Unitario ($P_{\\text{base}}$):** Precio inicial asignado a cada transacción contenida dentro de la primera bolsa.
    * **Tamaño Base de Bolsa ($T_1$):** Cantidad de transacciones incluidas en la primera bolsa comercial.
    * **Valor Fijo por Bolsa:** Cada bolsa adicional tiene exactamente el mismo costo fijo en dinero ($P_{\\text{base}} \\times T_1$).
    * **Curva Progresiva de Descuento por Volumen:** Aunque el valor en dinero por bolsa es constante, la cantidad de transacciones acomodadas dentro de cada bolsa subsecuente aumenta gradualmente. La curva parte de 0% de descuento y se aproxima hacia el descuento máximo especificado a medida que el volumen crece, alcanzando la mitad de dicho descuento máximo cuando el cliente transacciona la cantidad de transacciones fijada en $K$.
    """)

with st.expander("Idea central del modelo", expanded=False):
    st.markdown("""
    * **Parametros Gerenciales (Decisión Comercial):**
      * Licencia Base Fija (ILF), Tarifa Mínima Garantizada (MCB), Porcentajes de Mantenimiento y Soporte (MLF y PSF).
      * Descuento Máximo ($D_{\\max}$), Curvatura de Descuento ($K$), e ICLF Objetivos para clientes pequeños y grandes.
      * Opcionalmente, el Tamaño Base de Bolsa ($T_1$) si se fija manualmente por estrategia comercial.
    * **Parametros Optimizados Automaticamente:**
      * Tarifa Base Recurrente ($P_{\\text{base}}$) y opcionalmente el Tamaño Base ($T_1$).
    * **Objetivo de la Optimizacion:**
      * **Facilitar la entrada de clientes pequeños:** Al ofrecer tarifas iniciales y pisos de entrada moderados, se reduce la barrera de adopcion para capturar flujo recurrente de largo plazo.
      * **Preservar el valor de clientes grandes:** Garantiza que los nuevos clientes grandes mantengan precios de entrada acordes a su escala, evitando la perdida de ingresos que historicamente sabemos que están dispuestos a pagar.
    """)

def load_and_standardize_data(uploaded_file):
    """Carga y estandariza los datos de Excel/CSV a columnas homogéneas con Año y Mes."""
    if uploaded_file is not None:
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)
    else:
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

st.sidebar.header("1. Carga de Datos")
uploaded_file = st.sidebar.file_uploader(
    "Subir archivo (datos_facturacion.xlsx / CSV)",
    type=["xlsx", "csv"],
    help="Debe incluir columnas como 'cliente', 'producto', '# txn', 'valor cobrado' y opcionalmente 'año' y 'mes'."
)

df_raw = load_and_standardize_data(uploaded_file)

st.sidebar.header("2. Seleccion Obligatoria de Producto")

lista_productos = sorted(df_raw["producto"].unique().tolist())
if not lista_productos:
    lista_productos = ["General"]

prod_seleccionado = st.sidebar.selectbox(
    "Linea de Producto a Evaluar",
    lista_productos,
    index=0,
    help="El análisis se realiza de forma independiente por producto para mantener coherencia en las tarifas por bolsa."
)

st.sidebar.caption("Analisis restringido exclusivamente a: " + str(prod_seleccionado))

df_filtered_prod = df_raw[df_raw["producto"] == prod_seleccionado].copy()

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

df_filtered_time = df_filtered_prod.copy()
if anio_sel != "TODOS":
    df_filtered_time = df_filtered_time[df_filtered_time["año"] == int(anio_sel)]
if mes_sel != "TODOS":
    df_filtered_time = df_filtered_time[df_filtered_time["mes"] == int(mes_sel)]

st.sidebar.markdown("---")
eval_mode = st.sidebar.radio(
    "Modo de Evaluacion Recurrente",
    ["Promedio Mensual por Cliente", "Detalle Registros Filtrados"],
    help="Promedio Mensual por Cliente consolida el histórico de cada empresa a una tarifa mensual representativa."
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

st.sidebar.header("3. Ajuste del Modelo Recurrente")

with st.sidebar.expander("Parametros Recurrentes (MCLF + MCB)", expanded=True):
    Rev_target_pct = st.slider(
        "Meta de Recaudo vs Actual (%)",
        80, 150, 100, 5,
        help=(
            "Porcentaje de la facturación actual que se proyecta recuperar globalmente.\n"
            "• Al subir este %: El optimizador incrementa el precio base unitario para recaudar más dinero en total.\n"
            "• Al bajar este %: El optimizador reduce las tarifas para hacer la propuesta más competitiva a la baja."
        )
    ) / 100.0

    MCB_piso = st.number_input(
        "Cobro Minimo Mensual Garantizado (MCB piso COP)",
        value=1000000, step=100000,
        help=(
            "Tarifa fija mínima mensual no negociable.\n"
            "• Clientes cuyo cálculo por bolsas sea menor a este piso pagarán exactamente este monto."
        )
    )

    optimizar_T1 = st.checkbox(
        "Optimizar tamaño base de bolsa (T1) libremente",
        value=True,
        help=(
            "• Activado: El modelo busca matemáticamente la combinación idónea de T1 y Tarifa Base.\n"
            "• Desactivado: Defines un T1 fijo por estrategia comercial (ej. 1,000 txns) y el modelo optimiza solo la Tarifa Base."
        )
    )

    if not optimizar_T1:
        T1_fijo_user = st.number_input(
            "Tamaño Base de Bolsa Fijo (T1 txns)",
            value=1000, min_value=10, step=100,
            help="Capacidad fija asignada a la primera bolsa por decisión comercial."
        )
    else:
        T1_fijo_user = 1000

    optimizar_Dmax_K = st.checkbox(
        "Optimizar Descuento Maximo (D max) y Curvatura (K) libremente",
        value=False,
        help=(
            "• Activado: El optimizador ajusta D max y K además de T1 y Tarifa Base buscando el mejor ajuste al recaudo.\n"
            "• Desactivado: Usa los valores fijos definidos en los sliders siguientes como anclas comerciales."
        )
    )

    if not optimizar_Dmax_K:
        D_max = st.slider(
            "Descuento Maximo por Volumen (D max)",
            0.05, 1.00, 0.30, 0.05,
            help="Límite máximo teórico al que se aproxima el descuento por volumen."
        )

        k_sens = st.slider(
            "Curvatura de Descuento (K)",
            10, 5000, 500, 10,
            help="Es el número exacto de transacciones en el que se alcanza la mitad del descuento máximo (D max / 2). Controla que tan rapido crece el % de descuento en función del número de transacciones"
        )
    else:
        D_max = 0.30
        k_sens = 500

    pct_MLF = st.slider(
        "% Mantenimiento (MLF)",
        1.0, 10.0, 3.0, 0.5,
        help="Porcentaje sobre la Licencia Base (ILF) cobrado mensualmente por mantenimiento técnico."
    ) / 100.0

    pct_PSF = st.slider(
        "% Soporte (PSF)",
        5.0, 30.0, 15.0, 1.0,
        help="Porcentaje sobre la Licencia Base (ILF) cobrado mensualmente por soporte operativo."
    ) / 100.0

    st.markdown("---")
    st.markdown("**Pesos de la Funcion de Perdida (MCLF)**")
    peso_recaudo = st.slider(
        "Peso meta de recaudo global",
        0.0, 10.0, 1.0, 0.1,
        help=(
            "Penaliza la desviacion entre el recaudo simulado y la Meta de Recaudo global.\n"
            "• Alto (>=3): Mantiene el recaudo total cerca de la meta aunque el ajuste per-cliente se desajuste.\n"
            "• Bajo (<=0.5): Prioriza ajuste per-cliente; el recaudo global puede desviarse de la meta."
        )
    )

st.sidebar.header("4. Ajuste del Modelo Inicial (Setup)")
with st.sidebar.expander("Parametros de Entrada (ILF + ICLF)", expanded=True):
    ILF_base_param = st.number_input(
        "Licencia Base Fija (ILF base COP)",
        value=2500000, step=500000,
        help="Monto fijo de entrada cobrado a todo cliente por onboarding y parametrización inicial."
    )

    ICLF_target_small = st.number_input(
        "ICLF Objetivo para cliente pequeño (COP)",
        value=2000000, step=500000,
        help="Referencia orientativa de cobro inicial por capacidad (ICLF) para el cliente de menor volumen."
    )

    ICLF_target_large = st.number_input(
        "ICLF Objetivo para cliente grande (COP)",
        value=27500000, step=1000000,
        help="Meta de cobro inicial por capacidad (ICLF) para el cliente de mayor volumen de la cartera."
    )

    st.markdown("---")
    st.markdown("**Parametros de Descuento ICLF (Independientes del MCLF)**")

    D_max_ICLF = st.slider(
        "Descuento Maximo ICLF (D max ICLF)",
        0.05, 1.00, 0.30, 0.01,
        help=(
            "Límite máximo teórico al que se aproxima el descuento por volumen para el modelo ICLF.\n"
            "• Es independiente del D max del MCLF: puedes definir una agresividad comercial distinta para el setup inicial.\n"
            "• Al subir este %: las bolsas iniciales son mas largas (cobran igual pero cubren mas txns) para clientes grandes."
        )
    )

    k_sens_ICLF = st.slider(
        "Curvatura de Descuento ICLF (K ICLF)",
        100, 10000, 500, 100,
        help=(
            "Numero exacto de transacciones en el que se alcanza la mitad del descuento maximo D max ICLF / 2.\n"
            "• Es independiente de la curvatura K del MCLF.\n"
            "• Al subir este K: el descuento por volumen crece mas lentamente (curva mas plana)."
        )
    )

    optimizar_T1_ICLF = st.checkbox(
        "Optimizar tamaño base de bolsa ICLF (T1 ICLF) libremente",
        value=True,
        help=(
            "• Activado: El modelo busca matemáticamente la combinación idónea de T1 ICLF y Tarifa Base ICLF.\n"
            "• Desactivado: Defines un T1 ICLF fijo por estrategia comercial y el modelo optimiza solo la Tarifa Base ICLF."
        )
    )

    if not optimizar_T1_ICLF:
        T1_fijo_user_ICLF = st.number_input(
            "Tamaño Base de Bolsa ICLF Fijo (T1 ICLF txns)",
            value=1000, min_value=10, step=100,
            help="Capacidad fija asignada a la primera bolsa ICLF por decisión comercial."
        )
    else:
        T1_fijo_user_ICLF = 1000

def calc_bolsa_acum(b_idx, T1, Dmax, k):
    """Calcula las transacciones acumuladas alcanzadas hasta la bolsa b_idx."""
    if b_idx is None or T1 is None or Dmax is None or k is None:
        return 0.0
    try:
        T1 = float(T1); Dmax = float(Dmax); k = float(k); b_idx = float(b_idx)
        if b_idx <= 0 or T1 <= 0 or k <= 0:
            return 0.0
        d_eff = min(max(Dmax, 0.0), 0.999)
        with np.errstate(over='ignore', invalid='ignore', divide='ignore'):
            radicand = (T1 * b_idx - k)**2 + 4.0 * (1.0 - d_eff) * k * T1 * b_idx
            val = (T1 * b_idx - k) + np.sqrt(max(0.0, radicand))
            denom = 2.0 - 2.0 * d_eff
            if denom <= 0:
                return float('inf')
            result = val / denom
        if not np.isfinite(result):
            return 0.0
        return float(result)
    except (ValueError, TypeError, FloatingPointError, OverflowError):
        return 0.0

def calc_mclf_cliente(vol, P_base, T1, Dmax, k):
    """Calcula el cobro recurrente por bolsas para un volumen determinado."""
    if vol is None or vol <= 0 or P_base is None or T1 is None:
        return 0.0
    try:
        P_base = float(P_base); T1 = float(T1); Dmax = float(Dmax); k = float(k)
        if P_base <= 0 or T1 <= 0:
            return 0.0
        b = 1
        acum = calc_bolsa_acum(b, T1, Dmax, k)
        while acum < vol and b < 300:
            b += 1
            acum = calc_bolsa_acum(b, T1, Dmax, k)
        return b * (P_base * T1)
    except (ValueError, TypeError, FloatingPointError, OverflowError):
        return 0.0

def calc_num_bolsas(vol, T1, Dmax, k):
    """Calcula el número exacto de bolsas necesarias y la capacidad total alcanzada."""
    if vol is None or vol <= 0 or T1 is None:
        return 0, 0.0
    try:
        T1 = float(T1); Dmax = float(Dmax); k = float(k)
        if T1 <= 0:
            return 0, 0.0
        b = 1
        acum = calc_bolsa_acum(b, T1, Dmax, k)
        while acum < vol and b < 300:
            b += 1
            acum = calc_bolsa_acum(b, T1, Dmax, k)
        return b, acum
    except (ValueError, TypeError, FloatingPointError, OverflowError):
        return 0, 0.0

if len(df_filtered_time) > 0:
    _monthly_totals = df_filtered_time.groupby(["año", "mes"])["valor cobrado"].sum()
    rev_actual_total = float(_monthly_totals.mean())
    num_meses_disponibles = int(_monthly_totals.shape[0])
else:
    rev_actual_total = 0.0
    num_meses_disponibles = 0
target_rev_rec = rev_actual_total * Rev_target_pct

def loss_recurrente(params, opt_T1, T1_fijo, opt_DK, D_max_fijo, k_fijo, w_recaudo):
    try:
        p = list(params)
        P_base = float(p.pop(0))
        T1 = float(p.pop(0)) if opt_T1 else float(T1_fijo)
        D_max_eff = float(p.pop(0)) if opt_DK else float(D_max_fijo)
        k_sens_eff = float(p.pop(0)) if opt_DK else float(k_fijo)
    except (ValueError, TypeError, IndexError):
        return 1e15
    if not (np.isfinite(P_base) and np.isfinite(T1) and np.isfinite(D_max_eff) and np.isfinite(k_sens_eff)):
        return 1e15
    if P_base <= 0 or T1 <= 1:
        return 1e15
    if D_max_eff <= 0.001 or D_max_eff >= 0.999 or k_sens_eff <= 0:
        return 1e15

    recurrentes_nuevos = []
    for _, row in df_work.iterrows():
        mclf = calc_mclf_cliente(row["# txn"], P_base, T1, D_max_eff, k_sens_eff)
        mlf_psf = ILF_base_param * (pct_MLF + pct_PSF)
        tot = max(MCB_piso, mclf + mlf_psf)
        recurrentes_nuevos.append(tot)

    recurrentes_nuevos = np.array(recurrentes_nuevos, dtype=float)
    valores_actuales = df_work["valor cobrado"].values.astype(float)
    denom_cliente = np.maximum(1.0, valores_actuales)

    diffs_rel = (recurrentes_nuevos - valores_actuales) / denom_cliente
    mse_rel = float(np.mean(diffs_rel**2))

    if eval_mode == "Detalle Registros Filtrados":
        rev_sim = float(recurrentes_nuevos.sum() / max(1, num_meses_disponibles))
    else:
        rev_sim = float(recurrentes_nuevos.sum())
    rev_penalty_rel = ((target_rev_rec - rev_sim) / max(1.0, target_rev_rec))**2

    return mse_rel + w_recaudo * rev_penalty_rel

x0 = [500.0]
if optimizar_T1:
    x0.append(1000.0)
if optimizar_Dmax_K:
    x0.append(D_max)
    x0.append(k_sens)

res_rec = opt.minimize(
    loss_recurrente, x0=x0, method='Nelder-Mead',
    args=(optimizar_T1, T1_fijo_user, optimizar_Dmax_K, D_max, k_sens, peso_recaudo),
    options={'xatol': 1e-2, 'fatol': 1e-4, 'maxiter': 1000, 'disp': False}
)

_xres = list(res_rec.x)
P_base_MCLF_opt = max(10.0, float(_xres.pop(0)))
if optimizar_T1:
    T1_opt = max(10.0, float(_xres.pop(0)))
else:
    T1_opt = float(T1_fijo_user)
if optimizar_Dmax_K:
    D_max = min(0.999, max(0.05, float(_xres.pop(0))))
    k_sens = max(10.0, float(_xres.pop(0)))

costo_bolsa_mclf = P_base_MCLF_opt * T1_opt

vol_min = max(1, int(df_work["# txn"].min())) if len(df_work) > 0 else 1
vol_max = max(1, int(df_work["# txn"].max())) if len(df_work) > 0 else 1

if optimizar_T1_ICLF:
    _vol_min_iclf = int(vol_min)
    _vol_max_iclf = int(vol_max)
    _dmax_iclf = float(D_max_ICLF)
    _k_iclf = float(k_sens_ICLF)
    _iclf_t_small = float(ICLF_target_small)
    _iclf_t_large = float(ICLF_target_large)

    def loss_inicial(params, _vmn=_vol_min_iclf, _vmx=_vol_max_iclf, _dm=_dmax_iclf, _k=_k_iclf, _ts=_iclf_t_small, _tl=_iclf_t_large):
        try:
            P_base, T1 = params[0], params[1]
            P_base = float(P_base); T1 = float(T1)
        except (ValueError, TypeError, IndexError, KeyError, AttributeError):
            return 1e15
        if not (np.isfinite(P_base) and np.isfinite(T1)):
            return 1e15
        P_base = max(1.0, min(P_base, 1e7))
        T1 = max(10.0, min(T1, 1e6))
        if P_base <= 0 or T1 <= 1:
            return 1e15

        try:
            iclf_min_sim = calc_iclf_cliente(_vmn, P_base, T1, _dm, _k)
            iclf_max_sim = calc_iclf_cliente(_vmx, P_base, T1, _dm, _k)
        except Exception:
            return 1e15

        if not (np.isfinite(iclf_min_sim) and np.isfinite(iclf_max_sim)):
            return 1e15
        if iclf_min_sim <= 0 or iclf_max_sim <= 0:
            return 1e15

        try:
            err_min = ((iclf_min_sim - _ts) / max(1.0, _ts)) ** 2
            err_max = ((iclf_max_sim - _tl) / max(1.0, _tl)) ** 2
            total = err_min + err_max
        except Exception:
            return 1e15
        if not np.isfinite(total):
            return 1e15
        return total

    try:
        _init_b_max_iclf, _ = calc_num_bolsas(_vol_max_iclf, 1000.0, _dmax_iclf, _k_iclf)
    except Exception:
        _init_b_max_iclf = 1
    try:
        _init_b_max_iclf = max(1, int(_init_b_max_iclf) if _init_b_max_iclf else 1)
    except Exception:
        _init_b_max_iclf = 1
    try:
        _P_base_init_iclf = _iclf_t_large / (_init_b_max_iclf * 1000.0) if _init_b_max_iclf > 0 else 500.0
        _P_base_init_iclf = float(np.clip(_P_base_init_iclf, 1.0, 1e7))
    except Exception:
        _P_base_init_iclf = 500.0

    res_iclf = None
    try:
        res_iclf = opt.minimize(
            loss_inicial,
            x0=[_P_base_init_iclf, 1000.0],
            method='Nelder-Mead',
            options={'xatol': 1e-2, 'fatol': 1e-6, 'maxiter': 500, 'disp': False}
        )
    except Exception:
        res_iclf = None

    P_base_ICLF_opt = max(10.0, _P_base_init_iclf)
    T1_opt_ICLF = 1000.0
    if res_iclf is not None and hasattr(res_iclf, 'x'):
        try:
            _xarr = list(res_iclf.x)
            if len(_xarr) >= 2:
                _p0 = float(_xarr[0]); _t1v = float(_xarr[1])
                if np.isfinite(_p0) and np.isfinite(_t1v):
                    P_base_ICLF_opt = max(10.0, _p0)
                    T1_opt_ICLF = max(10.0, _t1v)
        except Exception:
            pass
    try:
        costo_bolsa_ICLF_opt = P_base_ICLF_opt * T1_opt_ICLF
    except Exception:
        costo_bolsa_ICLF_opt = max(1.0, P_base_ICLF_opt * 1000.0)
else:
    T1_opt_ICLF = float(T1_fijo_user_ICLF)
    b_max_iclf, _ = calc_num_bolsas(vol_max, T1_opt_ICLF, D_max_ICLF, k_sens_ICLF)
    b_max_iclf_eff = max(1, b_max_iclf)
    costo_bolsa_ICLF_opt = ICLF_target_large / b_max_iclf_eff
    P_base_ICLF_opt = costo_bolsa_ICLF_opt / T1_opt_ICLF if T1_opt_ICLF > 0 else 0.0

def calc_iclf_cliente(vol, P_base_iclf, T1, Dmax, k):
    """Calcula el cobro por capacidad inicial (ICLF) estrictamente por el número de bolsas requeridas."""
    if vol is None or vol <= 0 or P_base_iclf is None or T1 is None:
        return 0.0
    try:
        P_base_iclf = float(P_base_iclf); T1 = float(T1); Dmax = float(Dmax); k = float(k)
        if P_base_iclf <= 0 or T1 <= 0:
            return 0.0
        b, _ = calc_num_bolsas(vol, T1, Dmax, k)
        if b is None or b < 0:
            return 0.0
        return float(b) * (P_base_iclf * T1)
    except (ValueError, TypeError, FloatingPointError, OverflowError):
        return 0.0

df_res = df_work.copy()

df_res["MCLF_Nuevo"] = df_res["# txn"].apply(lambda v: calc_mclf_cliente(v, P_base_MCLF_opt, T1_opt, D_max, k_sens))
df_res["MLF_PSF"] = ILF_base_param * (pct_MLF + pct_PSF)
df_res["Recurrente_Nuevo"] = np.maximum(MCB_piso, df_res["MCLF_Nuevo"] + df_res["MLF_PSF"])
df_res["Diff_Recurrente"] = df_res["Recurrente_Nuevo"] - df_res["valor cobrado"]
df_res["Var_Pct_Recurrente"] = (df_res["Diff_Recurrente"] / np.maximum(1.0, df_res["valor cobrado"])) * 100.0
df_res["En_Piso_MCB"] = df_res["Recurrente_Nuevo"] == MCB_piso

df_res["ILF_Nuevo"] = ILF_base_param
df_res["ICLF_Nuevo"] = df_res["# txn"].apply(lambda v: calc_iclf_cliente(v, P_base_ICLF_opt, T1_opt_ICLF, D_max_ICLF, k_sens_ICLF))
df_res["Inicial_Simulado"] = df_res["ILF_Nuevo"] + df_res["ICLF_Nuevo"]

if eval_mode == "Detalle Registros Filtrados":
    rev_nueva_total = df_res['Recurrente_Nuevo'].sum() / max(1, num_meses_disponibles)
else:
    rev_nueva_total = df_res['Recurrente_Nuevo'].sum()
diff_total = rev_nueva_total - rev_actual_total
pct_variacion_total = (diff_total / max(1.0, rev_actual_total)) * 100.0

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Facturacion Actual", f"${rev_actual_total:,.0f} COP")
col2.metric("Facturacion Modelo Nuevo", f"${rev_nueva_total:,.0f} COP", delta=f"{pct_variacion_total:+.1f}%")
col3.metric("Tarifa Piso Mensual", f"${MCB_piso:,.0f} COP")
col4.metric("% en Tarifa Piso", f"{(df_res['En_Piso_MCB'].sum()/max(1, len(df_res)))*100:.1f}%")
col5.metric("Setup Total Simulado", f"${df_res['Inicial_Simulado'].sum():,.0f} COP")

st.markdown("---")

tab_exec, tab_rec, tab_init, tab_ltv, tab_data = st.tabs([
    "Resumen",
    "Recurrente",
    "Inicial",
    "Valor vitalicio",
    "Detalle cliente"
])

with tab_exec:
    st.subheader(f"Resumen de Impacto - Producto: {prod_seleccionado}")

    st.info(f"Configuracion Activa: Producto = {prod_seleccionado} | Año = {anio_sel} | Mes = {mes_sel} | Modo = {eval_mode}")

    st.markdown("### Estructura de Precios por Bolsas Optimizada")

    df_res_rec_summary = pd.DataFrame([
        {"Parametro": "Tarifa Base Recurrente (P_base, MCLF)", "Valor": f"${P_base_MCLF_opt:,.2f} COP/txn"},
        {"Parametro": "Capacidad Base de Bolsa (T1)", "Valor": f"{T1_opt:,.0f} transacciones " + ("(Optimizado automáticamente)" if optimizar_T1 else "(Fijado comercialmente)")},
        {"Parametro": "Descuento Maximo (D max)", "Valor": f"{D_max*100:.1f}% " + ("(Optimizado automáticamente)" if optimizar_Dmax_K else "(Fijado comercialmente)")},
        {"Parametro": "Curvatura de Descuento (K)", "Valor": f"{k_sens:,.0f} txns " + ("(Optimizado automáticamente)" if optimizar_Dmax_K else "(Fijado comercialmente)")},
        {"Parametro": "Precio Fijo por Bolsa Recurrente", "Valor": f"${costo_bolsa_mclf:,.0f} COP"}
    ])
    st.markdown("#### Modelo Recurrente Mensual (MCLF + MCB)")
    st.table(df_res_rec_summary)

    min_iclf = df_res["ICLF_Nuevo"].min()
    max_iclf = df_res["ICLF_Nuevo"].max()
    df_res_init_summary = pd.DataFrame([
        {"Parametro": "Licencia Base Fija (ILF base)", "Valor": f"${ILF_base_param:,.0f} COP"},
        {"Parametro": "Tarifa Base Inicial (P_base, ICLF)", "Valor": f"${P_base_ICLF_opt:,.2f} COP/txn"},
        {"Parametro": "Precio Fijo por Bolsa Inicial (ICLF)", "Valor": f"${costo_bolsa_ICLF_opt:,.0f} COP"},
        {"Parametro": "Rango de Cobro Inicial Total Simulado", "Valor": f"Entre ${ILF_base_param + min_iclf:,.0f} COP y ${ILF_base_param + max_iclf:,.0f} COP"}
    ])
    st.markdown("#### Modelo Inicial / Setup (ILF + ICLF)")
    st.table(df_res_init_summary)

    st.markdown("### Comparativa Global de Recaudo")
    fig_bar_exec = go.Figure(data=[
        go.Bar(name='Facturación Real Actual', x=['Recaudo Global'], y=[rev_actual_total], marker_color='gray'),
        go.Bar(name='Modelo Nuevo Proyectado', x=['Recaudo Global'], y=[rev_nueva_total], marker_color='teal')
    ])
    fig_bar_exec.update_layout(
        barmode='group',
        yaxis_title="Monto ($ COP)",
        height=320
    )
    st.plotly_chart(fig_bar_exec, use_container_width=True)

    if diff_total < 0:
        st.warning("Alerta: El recaudo proyectado cae por debajo del actual. Ajusta la Meta de Recaudo o la Tarifa Mínima.")
    else:
        st.success("Resultado Exitoso: El recaudo proyectado cubre o supera la meta fijada para este producto.")

with tab_rec:
    st.subheader("Analisis Recurrente: Facturacion Real vs Nuevo Modelo")

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
        title=f"Cobro Mensual por Cliente vs Volumen ({prod_seleccionado})",
        xaxis_title="Volumen Transaccional Mensual (# txn)",
        yaxis_title="Cobro Mensual ($ COP)",
        xaxis_type="log",
        height=420
    )
    st.plotly_chart(fig_rec, use_container_width=True)

    st.markdown("---")
    st.subheader("Distribucion de Impacto y Variacion en la Factura")

    df_res["Diff_Recurrente_Anual"] = df_res["Diff_Recurrente"] * 12.0
    df_res["valor_cobrado_Anual"] = df_res["valor cobrado"] * 12.0
    df_res["Recurrente_Nuevo_Anual"] = df_res["Recurrente_Nuevo"] * 12.0

    q1_var = df_res["Var_Pct_Recurrente"].quantile(0.25)
    q3_var = df_res["Var_Pct_Recurrente"].quantile(0.75)
    iqr_var = q3_var - q1_var

    if iqr_var > 0:
        outlier_mask = (df_res["Var_Pct_Recurrente"] > (q3_var + 3.0 * iqr_var)) | (df_res["Var_Pct_Recurrente"] < (q1_var - 3.0 * iqr_var))
    else:
        outlier_mask = df_res["Var_Pct_Recurrente"].abs() > 300.0

    df_outliers = df_res[outlier_mask]
    df_clean = df_res[~outlier_mask] if len(df_res[~outlier_mask]) > 0 else df_res.copy()

    if not df_outliers.empty:
        st.warning(f"**Atención - Outliers Extremos Detectados ({len(df_outliers)} cliente/s):**")
        for _, row_out in df_outliers.iterrows():
            st.markdown(
                f"* **{row_out['cliente']}**: Volumen = `{row_out['# txn']:,} txns` | Factura Actual = `${row_out['valor cobrado']:,.0f} COP/mes` | Factura Nueva = `${row_out['Recurrente_Nuevo']:,.0f} COP/mes` | **Variación = {row_out['Var_Pct_Recurrente']:+.1f}%**"
            )
        st.caption("Estos registros con variaciones atípicas se excluyen automáticamente de los gráficos de distribución a continuación para mantener la escala legible.")

    col_ctrl1, col_ctrl2 = st.columns(2)
    with col_ctrl1:
        vista_temporal = st.radio(
            "Temporalidad de la Factura",
            ["Mensual", "Anual"],
            horizontal=True,
            key="rec_vista_temporal"
        )
    with col_ctrl2:
        tipo_grafico = st.radio(
            "Tipo de Gráfico",
            ["Boxplot", "Histograma"],
            horizontal=True,
            key="rec_tipo_grafico"
        )

    val_col = "Diff_Recurrente" if vista_temporal == "Mensual" else "Diff_Recurrente_Anual"
    unit_label = "COP/mes" if vista_temporal == "Mensual" else "COP/año"

    col_g1, col_g2 = st.columns(2)

    with col_g1:
        if tipo_grafico == "Boxplot":
            fig_dist_cop = px.box(
                df_clean, y=val_col, points="all", hover_name="cliente",
                title=f"Distribucion de Diferencia en Factura ({vista_temporal} - $ COP)",
                labels={val_col: f"Diferencia en Factura ({unit_label})"},
                color_discrete_sequence=['darkcyan']
            )
        else:
            fig_dist_cop = px.histogram(
                df_clean, x=val_col, nbins=15, hover_name="cliente",
                title=f"Distribucion de Diferencia en Factura ({vista_temporal} - $ COP)",
                labels={val_col: f"Diferencia en Factura ({unit_label})"},
                color_discrete_sequence=['darkcyan']
            )
        fig_dist_cop.update_layout(height=360)
        st.plotly_chart(fig_dist_cop, use_container_width=True)

    with col_g2:
        if tipo_grafico == "Boxplot":
            fig_dist_pct = px.box(
                df_clean, y="Var_Pct_Recurrente", points="all", hover_name="cliente",
                title=f"Distribucion de Variacion % en Factura ({vista_temporal})",
                labels={"Var_Pct_Recurrente": "Variación % vs Factura Actual"},
                color_discrete_sequence=['teal']
            )
        else:
            fig_dist_pct = px.histogram(
                df_clean, x="Var_Pct_Recurrente", nbins=15, hover_name="cliente",
                title=f"Distribucion de Variacion % en Factura ({vista_temporal})",
                labels={"Var_Pct_Recurrente": "Variación % vs Factura Actual"},
                color_discrete_sequence=['teal']
            )
        fig_dist_pct.update_layout(height=360)
        st.plotly_chart(fig_dist_pct, use_container_width=True)

    st.markdown("---")
    st.markdown("### Tabla Escalar de Bolsas Recurrentes Mensuales (MCLF)")
    st.caption("Esta tabla ilustra la expansión progresiva de transacciones contenidas por bolsa y el costo acumulado.")

    bolsas_list = []
    prev_acum = 0
    for b in range(1, 11):
        acum_txns = calc_bolsa_acum(b, T1_opt, D_max, k_sens)
        txns_en_bolsa = acum_txns - prev_acum
        costo_total = b * costo_bolsa_mclf
        tarifa_efectiva = costo_total / acum_txns if acum_txns > 0 else 0
        desc_pct = (1 - (tarifa_efectiva / P_base_MCLF_opt)) * 100 if P_base_MCLF_opt > 0 else 0

        bolsas_list.append({
            "Bolsa #": f"Bolsa {b}",
            "Costo Fijo por Bolsa": costo_bolsa_mclf,
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
    st.subheader("Cobro Unico de Entrada (ILF + ICLF)")
    st.info("Representa el cobro único de onboarding como si los clientes ingresaran hoy como clientes nuevos.")

    df_init_unique = df_res.groupby("cliente").agg(
        txns_media=("# txn", "mean"),
        ILF_Nuevo=("ILF_Nuevo", "first"),
        ICLF_Nuevo=("ICLF_Nuevo", "mean"),
        Inicial_Simulado=("Inicial_Simulado", "mean")
    ).reset_index().sort_values("txns_media", ascending=True)

    fig_init = go.Figure()
    fig_init.add_trace(go.Bar(
        x=df_init_unique["cliente"], y=df_init_unique["ILF_Nuevo"],
        name="ILF (Licencia Base Fija)", marker_color="darkslategrey"
    ))
    fig_init.add_trace(go.Bar(
        x=df_init_unique["cliente"], y=df_init_unique["ICLF_Nuevo"],
        name="ICLF (Capacidad de Setup)", marker_color="sandybrown"
    ))
    fig_init.update_layout(
        barmode='stack',
        title=f"Estructura del Fee Unico de Entrada por Cliente ({prod_seleccionado})",
        xaxis_title="Clientes (Ordenados por Escala de Volumen)",
        yaxis_title="Cobro Inicial ($ COP)",
        height=420
    )
    st.plotly_chart(fig_init, use_container_width=True)

    fig_setup_scatter = px.scatter(
        df_init_unique, x="txns_media", y="Inicial_Simulado",
        text="cliente", hover_name="cliente",
        labels={"txns_media": "Volumen Transaccional Promedio (# txn)", "Inicial_Simulado": "Cobro Inicial Total ($ COP)"},
        title="Escalado del Setup Inicial vs Volumen",
        color_discrete_sequence=['coral']
    )
    fig_setup_scatter.update_traces(marker=dict(size=10))
    fig_setup_scatter.update_layout(height=380, xaxis_type="log")
    st.plotly_chart(fig_setup_scatter, use_container_width=True)

    st.markdown("### Metricas Clave del Setup Proyectado")
    c_s1, c_s2, c_s3 = st.columns(3)
    c_s1.metric("Setup Promedio", f"${df_init_unique['Inicial_Simulado'].mean():,.0f} COP")
    c_s2.metric("Setup Mínimo", f"${df_init_unique['Inicial_Simulado'].min():,.0f} COP")
    c_s3.metric("Setup Máximo", f"${df_init_unique['Inicial_Simulado'].max():,.0f} COP")

    st.markdown("---")
    st.markdown("### Tabla Escalar de Bolsas Iniciales (ICLF)")
    st.caption("Esta tabla ilustra cómo se estructuran las bolsas para el cobro por capacidad inicial de entrada.")

    bolsas_iclf_list = []
    prev_acum_iclf = 0
    for b in range(1, 11):
        acum_txns = calc_bolsa_acum(b, T1_opt_ICLF, D_max_ICLF, k_sens_ICLF)
        txns_en_bolsa = acum_txns - prev_acum_iclf
        costo_total_iclf = b * costo_bolsa_ICLF_opt
        tarifa_efectiva = costo_total_iclf / acum_txns if acum_txns > 0 else 0
        desc_pct = (1 - (tarifa_efectiva / P_base_ICLF_opt)) * 100 if P_base_ICLF_opt > 0 else 0

        bolsas_iclf_list.append({
            "Bolsa #": f"Bolsa {b}",
            "Costo Fijo por Bolsa ICLF": costo_bolsa_ICLF_opt,
            "Costo Acumulado ICLF": costo_total_iclf,
            "Capacidad Txn Acumulada": int(round(acum_txns)),
            "Txns Adicionales en esta Bolsa": int(round(txns_en_bolsa)),
            "Tarifa Promedio ($/txn)": tarifa_efectiva,
            "Descuento Efectivo (%)": max(0.0, desc_pct)
        })
        prev_acum_iclf = acum_txns

    df_bolsas_iclf_tbl = pd.DataFrame(bolsas_iclf_list)
    st.dataframe(
        df_bolsas_iclf_tbl.style.format({
            "Costo Fijo por Bolsa ICLF": "${:,.0f} COP",
            "Costo Acumulado ICLF": "${:,.0f} COP",
            "Capacidad Txn Acumulada": "{:,}",
            "Txns Adicionales en esta Bolsa": "{:,}",
            "Tarifa Promedio ($/txn)": "${:,.2f} COP",
            "Descuento Efectivo (%)": "{:.1f}%"
        }),
        use_container_width=True
    )

with tab_ltv:
    st.subheader("Valor Vitalicio del Cliente (LTV) y Analisis de Retencion")
    st.markdown("""
    Esta sección permite realizar pruebas de sensibilidad sobre la permanencia de la cartera y calcular el valor acumulado proyectado.
    """)

    col_ltv1, col_ltv2, col_ltv3 = st.columns(3)
    with col_ltv1:
        churn_pequeño = st.slider(
            "Churn Mensual Clientes Pequeños (%)",
            0.5, 6.0, 2.5, 0.1,
            help="Tasa estimada de cancelación mensual para clientes de volumen bajo."
        ) / 100.0
    with col_ltv2:
        churn_grande = st.slider(
            "Churn Mensual Clientes Grandes (%)",
            0.1, 2.5, 0.5, 0.1,
            help="Tasa estimada de cancelación mensual para clientes corporativos de alto volumen."
        ) / 100.0
    with col_ltv3:
        meses_ltv = st.slider(
            "Horizonte de Analisis LTV (Meses)",
            12, 48, 24, 6,
            help="Cantidad de meses proyectados para calcular el retorno total descontado por retención."
        )

    q33 = df_res["# txn"].quantile(0.33) if len(df_res) > 0 else 100
    q66 = df_res["# txn"].quantile(0.66) if len(df_res) > 0 else 1000

    def calc_churn(v):
        if v <= q33:
            return churn_pequeño
        elif v >= q66:
            return churn_grande
        else:
            return (churn_pequeño + churn_grande) / 2.0

    df_res["Churn_Est"] = df_res["# txn"].apply(calc_churn)
    df_res["LTV_Proyectado"] = df_res["Inicial_Simulado"] + (df_res["Recurrente_Nuevo"] / df_res["Churn_Est"]) * (1 - (1 - df_res["Churn_Est"])**meses_ltv)

    fig_ltv = px.scatter(
        df_res, x="# txn", y="LTV_Proyectado", size="Recurrente_Nuevo",
        hover_name="cliente", hover_data=["cliente", "Inicial_Simulado", "Recurrente_Nuevo"],
        log_x=True, title=f"LTV Proyectado a {meses_ltv} Meses para {prod_seleccionado}",
        color_discrete_sequence=['teal']
    )
    fig_ltv.update_layout(height=420)
    st.plotly_chart(fig_ltv, use_container_width=True)

with tab_data:
    st.subheader("Detalle Cliente")

    cliente_sel = st.selectbox("Selecciona un cliente para evaluar su impacto individual:", df_res["cliente"].unique())
    row_c = df_res[df_res["cliente"] == cliente_sel].iloc[0]

    col_c1, col_c2, col_c3, col_c4, col_c5 = st.columns(5)
    col_c1.metric("Linea Producto", str(row_c["producto"]))
    col_c2.metric("Volumen Transaccional", f"{row_c['# txn']:,} txns")
    col_c3.metric("Facturacion Actual", f"${row_c['valor cobrado']:,.0f} COP")
    col_c4.metric("Facturacion Recurrente", f"${row_c['Recurrente_Nuevo']:,.0f} COP", delta=f"{row_c['Var_Pct_Recurrente']:+.1f}%")
    col_c5.metric("Setup Inicial Simulado", f"${row_c['Inicial_Simulado']:,.0f} COP")

    st.markdown("---")
    st.markdown(f"### Desglose Tarifario para {row_c['cliente']}")

    vol_c = row_c["# txn"]

    b_c_mclf, acum_c_mclf = calc_num_bolsas(vol_c, T1_opt, D_max, k_sens)
    b_c_iclf, acum_c_iclf = calc_num_bolsas(vol_c, T1_opt_ICLF, D_max_ICLF, k_sens_ICLF)

    mclf_c = row_c["MCLF_Nuevo"]
    mlf_psf_c = row_c["MLF_PSF"]
    rec_tot_c = row_c["Recurrente_Nuevo"]

    ilf_c = row_c["ILF_Nuevo"]
    iclf_c = row_c["ICLF_Nuevo"]
    setup_tot_c = row_c["Inicial_Simulado"]

    col_det1, col_det2 = st.columns(2)

    with col_det1:
        st.markdown("#### Desglose Recurrente Mensual (MCLF + MCB)")

        df_rec_summary = pd.DataFrame([
            {"Concepto": "Bolsas Recurrentes Requeridas", "Valor": f"{b_c_mclf} bolsa(s) (Capacidad: {acum_c_mclf:,.0f} txns)"},
            {"Concepto": "Precio Fijo por Bolsa Recurrente", "Valor": f"${costo_bolsa_mclf:,.0f} COP (${P_base_MCLF_opt:,.2f}/txn)"},
            {"Concepto": "Subtotal Bolsas Recurrentes (MCLF)", "Valor": f"${mclf_c:,.0f} COP"},
            {"Concepto": "Mantenimiento y Soporte (MLF + PSF)", "Valor": f"${mlf_psf_c:,.0f} COP"},
            {"Concepto": "Aplica Tarifa Mínima Garantizada (MCB)", "Valor": "SÍ" if row_c["En_Piso_MCB"] else "NO"},
            {"Concepto": "Cobro Recurrente Total Aplicado", "Valor": f"${rec_tot_c:,.0f} COP"}
        ])
        st.table(df_rec_summary)

    with col_det2:
        st.markdown("#### Desglose Cobro Inicial (ILF + ICLF)")

        df_init_summary = pd.DataFrame([
            {"Concepto": "Bolsas Iniciales Requeridas", "Valor": f"{b_c_iclf} bolsa(s) (Capacidad: {acum_c_iclf:,.0f} txns)"},
            {"Concepto": "Precio Fijo por Bolsa Inicial (ICLF)", "Valor": f"${costo_bolsa_ICLF_opt:,.0f} COP (${P_base_ICLF_opt:,.2f}/txn)"},
            {"Concepto": "Subtotal Capacidad Inicial (ICLF)", "Valor": f"${iclf_c:,.0f} COP"},
            {"Concepto": "Licencia Base Fija (ILF)", "Valor": f"${ilf_c:,.0f} COP"},
            {"Concepto": "Cobro Unico de Entrada Total", "Valor": f"${setup_tot_c:,.0f} COP"},
            {"Concepto": "LTV Proyectado", "Valor": f"${row_c['LTV_Proyectado']:,.0f} COP"}
        ])
        st.table(df_init_summary)

    st.markdown("---")
    st.markdown(f"### Estructura de Bolsas Recurrentes (MCLF) - {row_c['cliente']} ({vol_c:,} txns)")

    client_mclf_list = []
    prev_a_mclf = 0
    for b in range(1, b_c_mclf + 1):
        acum_t = calc_bolsa_acum(b, T1_opt, D_max, k_sens)
        txns_b = acum_t - prev_a_mclf
        c_mclf_total = b * costo_bolsa_mclf
        tar_ef_mclf = c_mclf_total / acum_t if acum_t > 0 else 0
        desc_p = (1 - (tar_ef_mclf / P_base_MCLF_opt)) * 100 if P_base_MCLF_opt > 0 else 0

        client_mclf_list.append({
            "Bolsa #": f"Bolsa {b}",
            "Capacidad Txn Acumulada": int(round(acum_t)),
            "Txns Adicionales en Bolsa": int(round(txns_b)),
            "Costo Fijo Bolsa Recurrente": costo_bolsa_mclf,
            "Costo Acumulado MCLF": c_mclf_total,
            "Tarifa Recurrente Promedio ($/txn)": tar_ef_mclf,
            "Descuento Efectivo (%)": max(0.0, desc_p)
        })
        prev_a_mclf = acum_t

    df_client_mclf = pd.DataFrame(client_mclf_list)
    st.dataframe(
        df_client_mclf.style.format({
            "Capacidad Txn Acumulada": "{:,}",
            "Txns Adicionales en Bolsa": "{:,}",
            "Costo Fijo Bolsa Recurrente": "${:,.0f} COP",
            "Costo Acumulado MCLF": "${:,.0f} COP",
            "Tarifa Recurrente Promedio ($/txn)": "${:,.2f} COP",
            "Descuento Efectivo (%)": "{:.1f}%"
        }),
        use_container_width=True
    )

    st.markdown(f"### Estructura de Bolsas Iniciales (ICLF) - {row_c['cliente']} ({vol_c:,} txns)")

    client_iclf_list = []
    prev_a_iclf = 0
    for b in range(1, b_c_iclf + 1):
        acum_t = calc_bolsa_acum(b, T1_opt_ICLF, D_max_ICLF, k_sens_ICLF)
        txns_b = acum_t - prev_a_iclf
        c_iclf_total = b * costo_bolsa_ICLF_opt
        tar_ef_iclf = c_iclf_total / acum_t if acum_t > 0 else 0
        desc_p = (1 - (tar_ef_iclf / P_base_ICLF_opt)) * 100 if P_base_ICLF_opt > 0 else 0

        client_iclf_list.append({
            "Bolsa #": f"Bolsa {b}",
            "Capacidad Txn Acumulada": int(round(acum_t)),
            "Txns Adicionales en Bolsa": int(round(txns_b)),
            "Costo Fijo Bolsa Inicial": costo_bolsa_ICLF_opt,
            "Costo Acumulado ICLF": c_iclf_total,
            "Tarifa Inicial Promedio ($/txn)": tar_ef_iclf,
            "Descuento Efectivo (%)": max(0.0, desc_p)
        })
        prev_a_iclf = acum_t

    df_client_iclf = pd.DataFrame(client_iclf_list)
    st.dataframe(
        df_client_iclf.style.format({
            "Capacidad Txn Acumulada": "{:,}",
            "Txns Adicionales en Bolsa": "{:,}",
            "Costo Fijo Bolsa Inicial": "${:,.0f} COP",
            "Costo Acumulado ICLF": "${:,.0f} COP",
            "Tarifa Inicial Promedio ($/txn)": "${:,.2f} COP",
            "Descuento Efectivo (%)": "{:.1f}%"
        }),
        use_container_width=True
    )

    st.markdown("---")
    st.markdown("### Tabla de Cartera y Resultados de Simulacion")

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
        label="Descargar Simulacion Completa (CSV)",
        data=csv_buffer.getvalue(),
        file_name=f"simulacion_tarifaria_{prod_seleccionado}_{anio_sel}_{mes_sel}.csv",
        mime="text/csv"
    )
