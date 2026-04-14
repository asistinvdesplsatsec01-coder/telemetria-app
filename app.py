import streamlit as st
import pandas as pd
import numpy as np

def analizar_datos_pro(df):
    # 1. Preparación de datos
    df.columns = df.columns.str.strip()
    df['Fecha Hora'] = pd.to_datetime(df['Fecha Hora'], dayfirst=True, errors='coerce')
    df = df.dropna(subset=['Fecha Hora']).sort_values('Fecha Hora')
    
    # Parámetro: Diferencia mínima para abrir una anomalía (3 litros)
    UMBRAL_ANOMALIA = 3.0 
    
    eventos = []
    i = 0
    total_filas = len(df)

    while i < total_filas:
        # Detectar inicio de parada (Velocidad 0)
        if df.iloc[i]['Velocidad'] == 0:
            idx_inicio = i
            f_inicio = df.iloc[i]
            
            # Buscar el final de la parada (cuando el vehículo vuelve a moverse)
            j = i + 1
            while j < total_filas:
                f_act = df.iloc[j]
                # Se considera movimiento si Vel > 2 o el Odómetro cambia > 1 metro
                odo_diff = abs(f_act['Odometro'] - df.iloc[j-1]['Odometro'])
                if f_act['Velocidad'] > 2 or odo_diff > 1:
                    break
                j += 1
            
            idx_final = j - 1
            f_final = df.iloc[idx_final]
            
            # --- AUDITORÍA DE VENTANA (Balance Neto) ---
            comb_inicial_evento = f_inicio['Total combustible']
            comb_final_evento = f_final['Total combustible']
            diferencia_neta = round(comb_final_evento - comb_inicial_evento, 2)

            # Si el balance final de la parada muestra una pérdida o ganancia mayor al umbral
            if abs(diferencia_neta) >= UMBRAL_ANOMALIA:
                tipo_evento = "CARGA" if diferencia_neta > 0 else "DESCARGA/ROBO"
                
                eventos.append({
                    'Tipo': tipo_evento,
                    'PI': f_inicio['Fecha Hora'],
                    'PF': f_final['Fecha Hora'],
                    'L. Inicial': comb_inicial_evento,
                    'L. Final': comb_final_evento,
                    'Balance Neto (L)': diferencia_neta,
                    'Odo': f_final['Odometro']
                })
            
            i = j # Saltar al final de la parada procesada
        else:
            i += 1

    # --- CÁLCULOS DE BALANCE GENERAL ---
    dist_i = df['Odometro'].min()
    dist_f = df['Odometro'].max()
    dist_total = (dist_f - dist_i) / 1000 # Distancia en Km
    
    comb_i = df['Total combustible'].iloc[0]
    comb_f = df['Total combustible'].iloc[-1]
    
    df_ev = pd.DataFrame(eventos)
    
    # Sumatorias basadas en los balances netos de cada ventana
    total_cargado = df_ev[df_ev['Balance Neto (L)'] > 0]['Balance Neto (L)'].sum() if not df_ev.empty else 0
    total_robado = abs(df_ev[df_ev['Balance Neto (L)'] < 0]['Balance Neto (L)'].sum()) if not df_ev.empty else 0
    
    # Consumo Real (Lo que realmente se "gastó" del tanque)
    consumo_real = round((comb_i + total_cargado) - comb_f, 2)
    # Consumo Neto (Solo lo que pasó por los inyectores, restando lo que se perdió en paradas)
    consumo_neto = round(consumo_real - total_robado, 2)

    resumen_visual = [
        {"label": "Distancia (Km)", "valor": f"{dist_total:,.2f}", "formula": "Odo Final - Odo Inicial"},
        {"label": "Total Cargado (L)", "valor": f"{total_cargado:,.2f}", "formula": "Suma de balances (+) en paradas"},
        {"label": "Total Robado (L)", "valor": f"{total_robado:,.2f}", "formula": "Suma de balances (-) en paradas"},
        {"label": "Consumo Real (L)", "valor": f"{consumo_real:,.2f}", "formula": "(Ini + Cargas) - Final"},
        {"label": "Rend. Neto", "valor": f"{round(dist_total/consumo_neto, 2) if consumo_neto > 0 else 0} km/l", "formula": "Km / (Consumo Real - Robos)"}
    ]
    
    return resumen_visual, df_ev

# --- INTERFAZ STREAMLIT ---
st.set_page_config(page_title="Reporte de Combustible", layout="wide")

col_titulo, col_reglas = st.columns([2, 1])
with col_titulo:
    st.title("📋 Reporte de Combustible")
    st.write("Auditoría por **Balance Neto de Ventana** (Comparación Inicial vs Final en parada).")

with col_reglas:
    with st.expander("🔍 Lógica de Auditoría", expanded=True):
        st.markdown("""
        1. **Detección de Ventana:** Se activa cuando la velocidad es 0.
        2. **Balance Final:** No suma variaciones fila por fila; solo compara el nivel con el que entró a la parada vs con el que salió.
        3. **Resultado:** Si descargan 100L y cargan 70L, el reporte mostrará un robo neto de **-30L**.
        """)

file = st.file_uploader("Subir archivo CSV", type=['csv'])

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
        
        st.subheader("🚩 Detalle de Anomalías por Parada")
        if not eventos.empty:
            # Ordenamos por fecha y mostramos balance detallado
            st.table(eventos.sort_values('PI')[['Tipo', 'PI', 'PF', 'L. Inicial', 'L. Final', 'Balance Neto (L)', 'Odo']])
        else:
            st.info("No se detectaron faltantes ni cargas significativas en las paradas analizadas.")
            
    except Exception as e:
        st.error(f"Error al procesar el archivo: {e}")
