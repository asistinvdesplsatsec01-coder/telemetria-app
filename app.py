import streamlit as st
import pandas as pd
import numpy as np

def analizar_datos_pro(df):
    # Limpieza básica
    df.columns = df.columns.str.strip()
    df['Fecha Hora'] = pd.to_datetime(df['Fecha Hora'], dayfirst=True, errors='coerce')
    df = df.dropna(subset=['Fecha Hora']).sort_values('Fecha Hora')
    
    # Parámetros de sensibilidad
    UMBRAL_ANOMALIA = 3.0 # Diferencia mínima de litros para reportar la ventana
    
    eventos = []
    i = 0
    total_filas = len(df)

    while i < total_filas:
        # 1. Detectar inicio de parada (Velocidad 0)
        if df.iloc[i]['Velocidad'] == 0:
            idx_inicio = i
            f_inicio = df.iloc[i]
            
            # 2. Buscar el final de la parada (cuando vuelve a haber velocidad o cambia odo)
            j = i + 1
            while j < total_filas:
                f_act = df.iloc[j]
                # Si el camión se mueve (velocidad > 2 o cambio de odómetro real)
                odo_diff = f_act['Odometro'] - df.iloc[j-1]['Odometro']
                if f_act['Velocidad'] > 2 or odo_diff > 1:
                    break
                j += 1
            
            idx_final = j - 1
            f_final = df.iloc[idx_final]
            
            # 3. ANÁLISIS DE LA VENTANA (Balance de masa en la parada)
            comb_inicial_evento = f_inicio['Total combustible']
            comb_final_evento = f_final['Total combustible']
            diferencia_neta = round(comb_final_evento - comb_inicial_evento, 2)

            # Si hubo una variación importante durante la parada
            if abs(diferencia_neta) >= UMBRAL_ANOMALIA:
                # Determinamos el tipo según el balance neto
                tipo_evento = "CARGA" if diferencia_neta > 0 else "DESCARGA/ROBO"
                
                eventos.append({
                    'Tipo': tipo_evento,
                    'PI': f_inicio['Fecha Hora'],
                    'PF': f_final['Fecha Hora'],
                    'L. Inicial': comb_inicial_evento,
                    'L. Final': comb_final_evento,
                    'Diferencia (L)': diferencia_neta,
                    'Odo': f_final['Odometro']
                })
            
            i = j # Continuar buscando después de esta parada
        else:
            i += 1

    # --- BALANCE GENERAL DEL REPORTE ---
    dist_total = (df['Odometro'].max() - df['Odometro'].min()) / 1000
    comb_i, comb_f = df['Total combustible'].iloc[0], df['Total combustible'].iloc[-1]
    
    df_ev = pd.DataFrame(eventos)
    total_cargado = df_ev[df_ev['Diferencia (L)'] > 0]['Diferencia (L)'].sum() if not df_ev.empty else 0
    total_robado = abs(df_ev[df_ev['Diferencia (L)'] < 0]['Diferencia (L)'].sum()) if not df_ev.empty else 0
    
    # Consumo Real: Lo que bajó el tanque + lo que se cargó
    consumo_real = round((comb_i + total_cargado) - comb_f, 2)
    consumo_neto = round(consumo_real - total_robado, 2)

    resumen_visual = [
        {"label": "Distancia (Km)", "valor": f"{dist_total:,.2f}", "formula": "Odo Final - Odo Inicial"},
        {"label": "Total Cargado (L)", "valor": f"{total_cargado:,.2f}", "formula": "Suma de diferencias (+) en paradas"},
        {"label": "Total Robado (L)", "valor": f"{total_robado:,.2f}", "formula": "Suma de diferencias (-) en paradas"},
        {"label": "Consumo Real (L)", "valor": f"{consumo_real:,.2f}", "formula": "(Ini + Cargas) - Final"},
        {"label": "Rend. Neto", "valor": f"{round(distancia_total/consumo_neto,2) if consumo_neto > 0 else 0} km/l", "formula": "Km / (Consumo - Robos)"}
    ]
    
    return resumen_visual, df_ev

# --- INTERFAZ ---
st.set_page_config(page_title="Reporte de Combustible", layout="wide")

col_t, col_r = st.columns([2, 1])
with col_t:
    st.title("📋 Reporte de Combustible")
    st.write("Análisis por Balance de Ventana en Parada (Neto Inicial vs Final).")

with col_r:
    with st.expander("🔍 Lógica de Auditoría", expanded=True):
        st.markdown("""
        - **Ventana de Análisis:** Se abre automáticamente cuando la Velocidad es 0.
        - **Balance Neto:** Se compara el combustible al inicio de la parada contra el final.
        - **Anomalía:** Si la diferencia neta es > 3L o < -3L, se registra el evento.
        - **Caso Mixto:** Si cargan y roban en la misma parada, el reporte mostrará el **resultado neto** de esa ventana.
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
        
        st.subheader("🚩 Detalle de Eventos por Ventana (Diferencia Neta)")
        if not eventos.empty:
            # Mostramos las columnas clave para que el usuario vea el balance
            st.table(eventos[['Tipo', 'PI', 'PF', 'L. Inicial', 'L. Final', 'Diferencia (L)', 'Odo']])
        else:
            st.info("No se detectaron variaciones netas en las paradas.")
    except Exception as e:
        st.error(f"Error: {e}")
