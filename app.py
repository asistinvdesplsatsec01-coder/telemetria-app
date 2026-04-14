import streamlit as st
import pandas as pd
import numpy as np

def analizar_datos_pro(df):
    # 1. Limpieza de columnas (Eliminar espacios en blanco en los nombres de columna)
    df.columns = df.columns.str.strip()
    
    # 2. Conversión flexible de fecha (Corrige el error del Traceback)
    df['Fecha Hora'] = pd.to_datetime(df['Fecha Hora'], dayfirst=True, errors='coerce')
    df = df.dropna(subset=['Fecha Hora']).sort_values('Fecha Hora')
    
    # --- Parámetros de Auditoría ---
    UMBRAL_ROBO = -2.0  
    UMBRAL_CARGA = 15.0 
    TASA_MAX_RALENTI = 0.08 
    
    # 3. Cálculos de deltas
    df['diff_l'] = df['Total combustible'].diff()
    df['diff_t'] = df['Fecha Hora'].diff().dt.total_seconds() / 60
    # Evitar división por cero en el primer registro
    df['tasa'] = np.where(df['diff_t'] > 0, df['diff_l'] / df['diff_t'], 0)

    eventos = []
    evento_actual = None
    
    for i in range(1, len(df)):
        f = df.iloc[i]
        ant = df.iloc[i-1]
        
        # Lógica de Robos
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

        # Lógica de Cargas
        if f['diff_l'] > UMBRAL_CARGA:
            eventos.append({
                'Tipo': 'CARGA', 'PI': ant['Fecha Hora'], 'PF': f['Fecha Hora'], 
                'L_Ini': ant['Total combustible'], 'L_Fin': f['Total combustible'], 
                'Litros': round(f['diff_l'], 2), 'Odo': f['Odometro']
            })

    # --- CÁLCULO DE VALORES TOTALES ---
    distancia_total = (df['Odometro'].max() - df['Odometro'].min()) / 1000
    comb_inicial = df['Total combustible'].iloc[0]
    comb_final = df['Total combustible'].iloc[-1]
    
    df_ev = pd.DataFrame(eventos)
    total_cargado = df_ev[df_ev['Tipo'] == 'CARGA']['Litros'].sum() if not df_ev.empty else 0
    total_robado = abs(df_ev[df_ev['Tipo'] == 'DESCARGA/ROBO']['Litros'].sum()) if not df_ev.empty else 0
    
    consumo_total_real = round((comb_inicial + total_cargado) - comb_final, 2)
    # El consumo neto del motor es el total menos lo que se robaron
    consumo_motor_neto = round(consumo_total_real - total_robado, 2)
    
    rend_bruto = round(distancia_total / consumo_total_real, 2) if consumo_total_real > 0 else 0
    rend_neto = round(distancia_total / consumo_motor_neto, 2) if consumo_motor_neto > 0 else 0

    resumen = {
        'Distancia (Km)': distancia_total,
        'Inicial (L)': comb_inicial,
        'Cargado (L)': total_cargado,
        'Robado (L)': total_robado,
        'Consumo Real (L)': consumo_total_real,
        'Rend. Bruto': rend_bruto,
        'Rend. Neto': rend_neto
    }
    
    return resumen, df_ev

# --- INTERFAZ ---
st.set_page_config(page_title="Auditor Kenworth Pro", layout="wide")
st.title("📊 Auditoría de Combustible")

file = st.file_uploader("Sube tu CSV", type=['csv'])

if file:
    try:
        df_raw = pd.read_csv(file)
        resumen, eventos = analizar_datos_pro(df_raw)
        
        st.subheader("📋 Resumen de Operación")
        c = st.columns(len(resumen))
        for i, (k, v) in enumerate(resumen.items()):
            c[i].metric(k, v)
        
        st.subheader("🚩 Detalle de Eventos (PI / PF)")
        if not eventos.empty:
            st.dataframe(eventos[['Tipo', 'PI', 'PF', 'Litros', 'Odo']], use_container_width=True)
        else:
            st.info("No se detectaron robos ni cargas en este archivo.")
    except Exception as e:
        st.error(f"Error al procesar el archivo: {e}")
        st.info("Asegúrate de que el CSV tenga las columnas: Fecha Hora, Total combustible, Velocidad, Odometro")
