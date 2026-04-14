import streamlit as st
import pandas as pd
import numpy as np

def analizar_datos_pro(df):
    # 1. Limpieza y Formato
    df.columns = df.columns.str.strip()
    df['Fecha Hora'] = pd.to_datetime(df['Fecha Hora'], dayfirst=True, errors='coerce')
    df = df.dropna(subset=['Fecha Hora']).sort_values('Fecha Hora')
    
    # --- Parámetros de Auditoría ---
    UMBRAL_ANOMALIA = 3.0       # Diferencia mínima neta para reportar el evento
    UMBRAL_RUIDO_INICIAL = 2.0  # Si el incremento al detenerse es < 2L, se ignora
    
    eventos = []
    i = 0
    total_filas = len(df)
    
    while i < total_filas:
        # Detectar cuando el vehículo se detiene (Velocidad 0)
        if df.iloc[i]['Velocidad'] == 0:
            idx_inicio = i
            f_inicio = df.iloc[i]
            
            # --- REGLA DE FILTRO DE RUIDO (< 2L) ---
            proximo_idx = i + 1
            if proximo_idx < total_filas:
                f_siguiente = df.iloc[proximo_idx]
                salto_inmediato = f_siguiente['Total combustible'] - f_inicio['Total combustible']
                
                # Si el incremento es pequeño (ruido/oleaje), movemos el inicio para ignorarlo
                if 0 < salto_inmediato < UMBRAL_RUIDO_INICIAL:
                    f_inicio = f_siguiente
                    idx_inicio = proximo_idx

            # Buscar el final de la parada (cuando hay movimiento o cambio de odómetro)
            j = idx_inicio + 1
            while j < total_filas:
                f_act = df.iloc[j]
                # Se considera movimiento si Vel > 2 o el Odo cambia > 1 metro
                odo_diff = abs(f_act['Odometro'] - df.iloc[j-1]['Odometro'])
                if f_act['Velocidad'] > 2 or odo_diff > 1:
                    break
                j += 1
            
            idx_final = j - 1
            f_final = df.iloc[idx_final]
            
            # --- BALANCE NETO DE LA VENTANA (Auditoría Inicial vs Final) ---
            comb_ini_ventana = f_inicio['Total combustible']
            comb_fin_ventana = f_final['Total combustible']
            diff_neta = round(comb_fin_ventana - comb_ini_ventana, 2)

            # Registro de evento si supera el umbral de anomalía
            if abs(diff_neta) >= UMBRAL_ANOMALIA:
                tipo = "CARGA" if diff_neta > 0 else "DESCARGA/ROBO"
                eventos.append({
                    'Tipo': tipo,
                    'PI': f_inicio['Fecha Hora'],
                    'PF': f_final['Fecha Hora'],
                    'L. Inicial': comb_ini_ventana,
                    'L. Final': comb_fin_ventana,
                    'Diferencia (L)': diff_neta,
                    'Odo': f_final['Odometro']
                })
            
            i = j # Continuar el análisis después de la parada procesada
        else:
            i += 1

    # --- CÁLCULOS FINALES ---
    dist_total = (df['Odometro'].max() - df['Odometro'].min()) / 1000
    comb_i, comb_f = df['Total combustible'].iloc[0], df['Total combustible'].iloc[-1]
    
    df_ev = pd.DataFrame(eventos)
    total_cargado = df_ev[df_ev['Diferencia (L)'] > 0]['Diferencia (L)'].sum() if not df_ev.empty else 0
    total_robado = abs(df_ev[df_ev['Diferencia (L)'] < 0]['Diferencia (L)'].sum()) if not df_ev.empty else 0
    
    # Consumo Real: Gasto total del tanque considerando lo que se le rellenó
    consumo_real = round((comb_i + total_cargado) - comb_f, 2)
    # Consumo Neto: Gasto atribuido solo al motor (restando extracciones)
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
    st.write("Análisis de balance neto por ventana con auditoría de incremento inicial.")

with col_reglas:
    with st.expander("🔍 Reglas de Validación Aplicadas", expanded=True):
        st.markdown("""
        1. **Filtro de Ruido Inicial:** Si al detenerse el combustible sube **< 2L**, se ignora ese salto (considerado oleaje). Si es **> 2L**, se incluye como parte del balance de carga.
        2. **Ventana de Parada:** El análisis inicia cuando Velocidad = 0 y termina cuando hay movimiento real (Vel > 2 o cambio de Odómetro).
        3. **Balance Neto:** No suma variaciones fila por fila. Compara el nivel con el que **llegó** (PI) vs con el que **se fue** (PF).
        4. **Umbral de Anomalía:** Solo se reportan eventos donde la diferencia neta de la parada sea mayor a **3 litros**.
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
        
        st.subheader("🚩 Detalle de Anomalías Detectadas")
        if not eventos.empty:
            st.table(eventos.sort_values('PI')[['Tipo', 'PI', 'PF', 'L. Inicial', 'L. Final', 'Diferencia (L)', 'Odo']])
        else:
            st.info("No se detectaron anomalías con los parámetros de validación actuales.")
            
    except Exception as e:
        st.error(f"Error al procesar el archivo: {e}")
