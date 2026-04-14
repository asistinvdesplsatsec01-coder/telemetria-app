import streamlit as st
import pandas as pd
import numpy as np

def analizar_datos_pro(df):
    # Estandarización de columnas (para que funcione con cualquier CSV de tu sistema)
    df['Fecha Hora'] = pd.to_datetime(df['Fecha Hora'])
    df = df.sort_values('Fecha Hora')
    
    # --- Parámetros de Auditoría ---
    UMBRAL_ROBO = -2.0  # Mínimo de litros para marcar como robo
    UMBRAL_CARGA = 15.0 # Mínimo de litros para marcar como carga
    TASA_MAX_RALENTI = 0.08 # L/min (Consumo máximo físico de un Kenworth 2015 parado)
    
    # Cálculos de deltas
    df['diff_l'] = df['Total combustible'].diff()
    df['diff_t'] = df['Fecha Hora'].diff().dt.total_seconds() / 60
    df['dist_km'] = df['Odometro'].diff() / 1000 # Asumiendo metros en el CSV
    df['tasa'] = df['diff_l'] / df['diff_t']

    eventos = []
    evento_actual = None
    
    # Lógica de detección de Ventanas (PI/PF)
    for i in range(1, len(df)):
        f = df.iloc[i]
        ant = df.iloc[i-1]
        
        # 1. Detección de Descargas/Robos
        if (f['Velocidad'] == 0) and (f['diff_l'] < -0.1) and (abs(f['tasa']) > TASA_MAX_RALENTI):
            if evento_actual is None:
                evento_actual = {'Tipo': 'DESCARGA/ROBO', 'PI': ant['Fecha Hora'], 'L_Ini': ant['Total combustible'], 'Odo': f['Odometro']}
            evento_actual['PF'] = f['Fecha Hora']
            evento_actual['L_Fin'] = f['Total combustible']
        else:
            if evento_actual is not None:
                total = round(evento_actual['L_Fin'] - evento_actual['L_Ini'], 2)
                if total <= UMBRAL_ROBO:
                    evento_actual['Litros'] = total
                    eventos.append(evento_actual)
                evento_actual = None

        # 2. Detección de Cargas
        if f['diff_l'] > UMBRAL_CARGA:
            eventos.append({
                'Tipo': 'CARGA',
                'PI': ant['Fecha Hora'],
                'PF': f['Fecha Hora'],
                'L_Ini': ant['Total combustible'],
                'L_Fin': f['Total combustible'],
                'Litros': round(f['diff_l'], 2),
                'Odo': f['Odometro']
            })

    # --- CÁLCULO DE VALORES TOTALES ---
    distancia_total = (df['Odometro'].max() - df['Odometro'].min()) / 1000
    comb_inicial = df['Total combustible'].iloc[0]
    comb_final = df['Total combustible'].iloc[-1]
    
    df_ev = pd.DataFrame(eventos)
    total_cargado = df_ev[df_ev['Tipo'] == 'CARGA']['Litros'].sum() if not df_ev.empty else 0
    total_robado = df_ev[df_ev['Tipo'] == 'DESCARGA/ROBO']['Litros'].sum() if not df_ev.empty else 0
    
    consumo_total_real = (comb_inicial + total_cargado) - comb_final
    consumo_motor_neto = consumo_total_real + total_robado # Sumamos el negativo del robo
    
    rendimiento_bruto = distancia_total / consumo_total_real if consumo_total_real > 0 else 0
    rendimiento_neto = distancia_total / consumo_motor_neto if consumo_motor_neto > 0 else 0

    resumen = {
        'Distancia Total (Km)': round(distancia_total, 2),
        'Combustible Inicial (L)': round(comb_inicial, 2),
        'Total Cargado (L)': round(total_cargado, 2),
        'Total Descargas (L)': round(total_robado, 2),
        'Consumo Total Real (L)': round(consumo_total_real, 2),
        'Rendimiento Bruto (Km/L)': round(rendimiento_bruto, 2),
        'Rendimiento Neto (Sin robos) (Km/L)': round(rendimiento_neto, 2)
    }
    
    return resumen, df_ev

# --- INTERFAZ STREAMLIT ---
st.set_page_config(page_title="Auditor de Combustible Pro", layout="wide")
st.title("📊 Auditoría de Combustible y Telemetría")

file = st.file_uploader("Arrastra tu reporte CSV aquí", type=['csv'])

if file:
    df_raw = pd.read_csv(file)
    resumen, eventos = analizar_datos_pro(df_raw)
    
    # Mostrar Totales en Columnas
    st.subheader("📋 Resumen General")
    cols = st.columns(len(resumen))
    for i, (k, v) in enumerate(resumen.items()):
        cols[i].metric(k, v)
    
    # Mostrar Tabla de Eventos PI/PF
    st.subheader("🚩 Eventos de Carga y Descarga (PI / PF)")
    if not eventos.empty:
        st.dataframe(eventos[['Tipo', 'PI', 'PF', 'Litros', 'Odo']], use_container_width=True)
    else:
        st.info("No se detectaron anomalías.")
