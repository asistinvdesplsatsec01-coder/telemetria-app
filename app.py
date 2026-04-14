import streamlit as st
import pandas as pd
import numpy as np

def analizar_datos_pro(df):
    # 1. Limpieza y Formato
    df.columns = df.columns.str.strip()
    df['Fecha Hora'] = pd.to_datetime(df['Fecha Hora'], dayfirst=True, errors='coerce')
    df = df.dropna(subset=['Fecha Hora']).sort_values('Fecha Hora')
    
    # --- Parámetros de Auditoría por Tanque ---
    UMBRAL_VARIACION_TANQUE = 3.0 # Litros para considerar movimiento en un solo tanque
    eventos = []
    
    # 2. Análisis de flujos independientes
    # Creamos columnas de diferencia por tanque
    df['diff_t1'] = df['Tanque 1'].diff()
    df['diff_t2'] = df['Tanque 2'].diff()
    
    i = 0
    while i < len(df) - 1:
        f_inicio = df.iloc[i]
        # Validación de Odómetro estático
        odo_cambio = abs(df.iloc[i]['Odometro'] - df.iloc[i-1]['Odometro']) if i > 0 else 0
        
        if f_inicio['Velocidad'] == 0 and odo_cambio <= 1:
            inicio_v = f_inicio['Fecha Hora']
            t1_ini, t2_ini = f_inicio['Tanque 1'], f_inicio['Tanque 2']
            
            k = i + 1
            while k < len(df):
                f_act = df.iloc[k]
                if f_act['Velocidad'] > 2 or abs(f_act['Odometro'] - df.iloc[k-1]['Odometro']) > 1:
                    break
                
                # Cálculo de deltas independientes
                delta_t1 = f_act['Tanque 1'] - t1_ini
                delta_t2 = f_act['Tanque 2'] - t2_ini
                delta_total = f_act['Total combustible'] - (t1_ini + t2_ini)

                # DETECCIÓN DE TRASIEGO O ROBO COMPENSADO
                # Si un tanque baja y el otro sube significativamente
                if (delta_t1 < -UMBRAL_VARIACION_TANQUE and delta_t2 > 1.0) or \
                   (delta_t2 < -UMBRAL_VARIACION_TANQUE and delta_t1 > 1.0):
                    eventos.append({
                        'Tipo': 'TRASIEGO / COMPENSACIÓN',
                        'PI': inicio_v, 'PF': f_act['Fecha Hora'],
                        'Detalle': f"T1: {round(delta_t1,2)}L | T2: {round(delta_t2,2)}L",
                        'Litros Netos': round(delta_total, 2),
                        'Odo': f_act['Odometro']
                    })
                    break

                # DETECCIÓN DE ROBO ESTÁNDAR (Diferencia Neta)
                elif delta_total <= -5.0:
                    eventos.append({
                        'Tipo': 'DESCARGA/ROBO',
                        'PI': inicio_v, 'PF': f_act['Fecha Hora'],
                        'Detalle': f"Baja total: {round(delta_total,2)}L",
                        'Litros Netos': round(delta_total, 2),
                        'Odo': f_act['Odometro']
                    })
                    break
                k += 1
            i = k
        else:
            i += 1

    # --- CÁLCULOS DE BALANCE ---
    dist_total = (df['Odometro'].max() - df['Odometro'].min()) / 1000
    comb_i = df['Total combustible'].iloc[0]
    comb_f = df['Total combustible'].iloc[-1]
    
    df_ev = pd.DataFrame(eventos)
    total_robado = abs(df_ev[df_ev['Tipo'].str.contains('ROBO|TRASIEGO')]['Litros Netos'].sum()) if not df_ev.empty else 0
    
    resumen_visual = [
        {"label": "Distancia (Km)", "valor": f"{dist_total:,.2f}", "formula": "Odo Final - Odo Inicial"},
        {"label": "Robado Neto (L)", "valor": f"{total_robado:,.2f}", "formula": "Pérdida neta acumulada"},
        {"label": "Consumo Real (L)", "valor": f"{round((comb_i - comb_f),2)}", "formula": "(Ini + Cargas) - Final"},
        {"label": "Rend. Neto", "valor": f"{round(dist_total/(comb_i-comb_f+0.1),2)} km/l", "formula": "Km / (Consumo - Robos)"}
    ]
    
    return resumen_visual, df_ev

# --- INTERFAZ ---
st.set_page_config(page_title="Reporte de Combustible", layout="wide")

col_t, col_r = st.columns([2, 1])
with col_t:
    st.title("📋 Reporte de Combustible")
    st.subheader("Auditoría de Tanques Independientes")

with col_r:
    with st.expander("🔍 Reglas de Validación", expanded=True):
        st.markdown("""
        1. **Análisis Dual:** Se monitorea Tanque 1 y Tanque 2 por separado.
        2. **Detección de Trasiego:** Identifica si el combustible "brinca" de un tanque a otro.
        3. **Estabilidad:** Solo analiza con Velocidad 0 y Odómetro fijo.
        """)

file = st.file_uploader("Subir CSV", type=['csv'])

if file:
    try:
        df_raw = pd.read_csv(file)
        resumen, eventos = analizar_datos_pro(df_raw)
        
        st.subheader("📊 Balance General")
        cols = st.columns(len(resumen))
        for i, item in enumerate(resumen):
            with cols[i]:
                st.metric(label=item["label"], value=item["valor"])
                st.caption(f"fx: {item['formula']}")
        
        st.subheader("🚩 Eventos Detectados (Incluye trasiegos)")
        if not eventos.empty:
            st.table(eventos[['Tipo', 'PI', 'PF', 'Detalle', 'Litros Netos']])
        else:
            st.info("No se detectaron anomalías.")
    except Exception as e:
        st.error(f"Error: {e}")
