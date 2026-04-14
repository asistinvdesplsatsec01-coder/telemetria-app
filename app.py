import streamlit as st
import pandas as pd
import numpy as np

def analizar_datos_pro(df):
    # 1. Limpieza y Formato
    df.columns = df.columns.str.strip()
    df['Fecha Hora'] = pd.to_datetime(df['Fecha Hora'], dayfirst=True, errors='coerce')
    df = df.dropna(subset=['Fecha Hora']).sort_values('Fecha Hora')
    
    # 2. Parámetros de Auditoría Ajustados
    # Bajamos la sensibilidad para detectar extracciones lentas o con motor apagado
    UMBRAL_ROBO = -5.0  
    UMBRAL_CARGA = 15.0 
    
    df['diff_l'] = df['Total combustible'].diff()
    
    eventos = []
    
    # --- NUEVA LÓGICA DE DETECCIÓN POR SALTOS ---
    # Buscamos cambios significativos entre registros sin importar la velocidad
    i = 0
    while i < len(df) - 1:
        inicio_idx = i
        current_l = df.iloc[i]['Total combustible']
        
        # Buscar el final de una tendencia (bajada o subida)
        j = i + 1
        while j < len(df):
            next_l = df.iloc[j]['Total combustible']
            diff = next_l - current_l
            
            # Si hay un cambio brusco acumulado con Velocidad 0
            if df.iloc[j]['Velocidad'] == 0:
                # Detectar Carga
                if diff > UMBRAL_CARGA:
                    # Verificar si la carga sigue subiendo
                    while j < len(df)-1 and df.iloc[j+1]['Total combustible'] >= next_l:
                        j += 1
                        next_l = df.iloc[j]['Total combustible']
                    
                    eventos.append({
                        'Tipo': 'CARGA',
                        'PI': df.iloc[inicio_idx]['Fecha Hora'],
                        'PF': df.iloc[j]['Fecha Hora'],
                        'Litros': round(df.iloc[j]['Total combustible'] - df.iloc[inicio_idx]['Total combustible'], 2),
                        'Odo': df.iloc[j]['Odometro']
                    })
                    break
                
                # Detectar Descarga (Robo)
                elif diff < UMBRAL_ROBO:
                    # Verificar si la descarga sigue bajando
                    while j < len(df)-1 and df.iloc[j+1]['Total combustible'] <= next_l:
                        j += 1
                        next_l = df.iloc[j]['Total combustible']
                        
                    total_descarga = df.iloc[j]['Total combustible'] - df.iloc[inicio_idx]['Total combustible']
                    if total_descarga <= UMBRAL_ROBO:
                        eventos.append({
                            'Tipo': 'DESCARGA/ROBO',
                            'PI': df.iloc[inicio_idx]['Fecha Hora'],
                            'PF': df.iloc[j]['Fecha Hora'],
                            'Litros': round(total_descarga, 2),
                            'Odo': df.iloc[j]['Odometro']
                        })
                    break
            
            # Si el camión se mueve, romper la búsqueda de evento estático
            if df.iloc[j]['Velocidad'] > 5:
                break
            j += 1
        i = j

    # --- BALANCE TOTAL ---
    distancia_total = (df['Odometro'].max() - df['Odometro'].min()) / 1000
    comb_inicial = df['Total combustible'].iloc[0]
    comb_final = df['Total combustible'].iloc[-1]
    
    df_ev = pd.DataFrame(eventos)
    total_cargado = df_ev[df_ev['Tipo'] == 'CARGA']['Litros'].sum() if not df_ev.empty else 0
    total_robado = abs(df_ev[df_ev['Tipo'] == 'DESCARGA/ROBO']['Litros'].sum()) if not df_ev.empty else 0
    
    # Consumo total reportado por los tanques
    consumo_total_real = round((comb_inicial + total_cargado) - comb_final, 2)
    # Consumo que realmente pasó por los inyectores (restando el robo)
    consumo_motor_neto = round(consumo_total_real - total_robado, 2)
    
    rend_bruto = round(distancia_total / consumo_total_real, 2) if consumo_total_real > 0 else 0
    rend_neto = round(distancia_total / consumo_motor_neto, 2) if consumo_motor_neto > 0 else 0

    resumen = {
        'Distancia (Km)': f"{distancia_total:,.2f}",
        'Inicial (L)': f"{comb_inicial:,.2f}",
        'Cargado (L)': f"{total_cargado:,.2f}",
        'Robado (L)': f"{total_robado:,.2f}",
        'Rend. Bruto': f"{rend_bruto} km/l",
        'Rend. Neto': f"{rend_neto} km/l"
    }
    
    return resumen, df_ev

# --- INTERFAZ ---
st.set_page_config(page_title="Auditor Kenworth Pro", layout="wide")
st.title("📊 Auditoría de Combustible v2.0")

file = st.file_uploader("Sube tu reporte CSV", type=['csv'])

if file:
    try:
        df_raw = pd.read_csv(file)
        resumen, eventos = analizar_datos_pro(df_raw)
        
        st.subheader("📋 Balance de Masa Total")
        cols = st.columns(len(resumen))
        for i, (k, v) in enumerate(resumen.items()):
            cols[i].metric(k, v)
        
        st.subheader("🚩 Ventanas de Eventos Detectadas")
        if not eventos.empty:
            # Ordenar por fecha para que sea legible
            eventos = eventos.sort_values('PI')
            st.table(eventos[['Tipo', 'PI', 'PF', 'Litros', 'Odo']])
        else:
            st.info("No se detectaron eventos sospechosos.")
            
    except Exception as e:
        st.error(f"Error crítico: {e}")
