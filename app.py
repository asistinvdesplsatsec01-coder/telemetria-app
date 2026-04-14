import streamlit as st
import pandas as pd
import numpy as np

def analizar_datos_pro(df):
    # 1. Limpieza y Formato
    df.columns = df.columns.str.strip()
    df['Fecha Hora'] = pd.to_datetime(df['Fecha Hora'], dayfirst=True, errors='coerce')
    df = df.dropna(subset=['Fecha Hora']).sort_values('Fecha Hora')
    
    # --- Parámetros de Auditoría ---
    UMBRAL_ROBO = -4.0  
    UMBRAL_CARGA = 15.0 
    MINUTOS_ESTABILIZACION = 3 
    
    eventos = []
    i = 0
    
    while i < len(df) - 1:
        f_inicio = df.iloc[i]
        odo_cambio = abs(df.iloc[i]['Odometro'] - df.iloc[i-1]['Odometro']) if i > 0 else 0
        
        if f_inicio['Velocidad'] == 0 and odo_cambio <= 1:
            hora_estabilizada = f_inicio['Fecha Hora'] + pd.Timedelta(minutes=MINUTOS_ESTABILIZACION)
            j = i
            while j < len(df) - 1 and df.iloc[j]['Fecha Hora'] < hora_estabilizada:
                j += 1
            
            if j >= len(df) - 1: break
            
            f_estable = df.iloc[j]
            k = j + 1
            while k < len(df):
                f_actual = df.iloc[k]
                cambio_odo_k = abs(f_actual['Odometro'] - df.iloc[k-1]['Odometro'])
                if f_actual['Velocidad'] > 2 or cambio_odo_k > 1:
                    break
                
                diff_acumulada = f_actual['Total combustible'] - f_estable['Total combustible']
                
                if diff_acumulada <= UMBRAL_ROBO:
                    while k < len(df)-1 and df.iloc[k+1]['Total combustible'] <= f_actual['Total combustible'] and df.iloc[k+1]['Velocidad'] == 0:
                        k += 1
                        f_actual = df.iloc[k]
                    eventos.append({'Tipo': 'DESCARGA/ROBO', 'PI': f_estable['Fecha Hora'], 'PF': f_actual['Fecha Hora'], 'Litros': round(f_actual['Total combustible'] - f_estable['Total combustible'], 2), 'Odo': f_actual['Odometro']})
                    break
                elif diff_acumulada >= UMBRAL_CARGA:
                    while k < len(df)-1 and df.iloc[k+1]['Total combustible'] >= f_actual['Total combustible'] and df.iloc[k+1]['Velocidad'] == 0:
                        k += 1
                        f_actual = df.iloc[k]
                    eventos.append({'Tipo': 'CARGA', 'PI': f_estable['Fecha Hora'], 'PF': f_actual['Fecha Hora'], 'Litros': round(f_actual['Total combustible'] - f_estable['Total combustible'], 2), 'Odo': f_actual['Odometro']})
                    break
                k += 1
            i = k
        else:
            i += 1

    # --- CÁLCULOS FINALES CON FÓRMULAS ---
    dist_i = df['Odometro'].min()
    dist_f = df['Odometro'].max()
    distancia_total = (dist_f - dist_i) / 1000
    
    comb_i = df['Total combustible'].iloc[0]
    comb_f = df['Total combustible'].iloc[-1]
    
    df_ev = pd.DataFrame(eventos)
    total_cargado = df_ev[df_ev['Tipo'] == 'CARGA']['Litros'].sum() if not df_ev.empty else 0
    total_robado = abs(df_ev[df_ev['Tipo'] == 'DESCARGA/ROBO']['Litros'].sum()) if not df_ev.empty else 0
    
    # Consumo Real: Lo que bajó el tanque considerando lo que se le puso
    consumo_total_real = round((comb_i + total_cargado) - comb_f, 2)
    # Consumo Neto: Consumo total menos lo que no pasó por el motor (robos)
    consumo_motor_neto = round(consumo_total_real - total_robado, 2)
    
    rend_bruto = round(distancia_total / consumo_total_real, 2) if consumo_total_real > 0 else 0
    rend_neto = round(distancia_total / consumo_motor_neto, 2) if consumo_motor_neto > 0 else 0

    resumen_visual = [
        {"label": "Distancia (Km)", "valor": f"{distancia_total:,.2f}", "formula": "Odo Final - Odo Inicial"},
        {"label": "Cargado (L)", "valor": f"{total_cargado:,.2f}", "formula": "Suma de eventos > 15L"},
        {"label": "Robado (L)", "valor": f"{total_robado:,.2f}", "formula": "Suma de eventos < -4L"},
        {"label": "Consumo Real (L)", "valor": f"{consumo_total_real:,.2f}", "formula": "(Ini + Cargas) - Final"},
        {"label": "Rend. Bruto", "valor": f"{rend_bruto} km/l", "formula": "Km / Consumo Real"},
        {"label": "Rend. Neto", "valor": f"{rend_neto} km/l", "formula": "Km / (Consumo Real - Robos)"}
    ]
    
    return resumen_visual, df_ev

# --- INTERFAZ ---
st.set_page_config(page_title="Reporte de Combustible", layout="wide")

col_titulo, col_reglas = st.columns([2, 1])

with col_titulo:
    st.title("📋 Reporte de Combustible")
    st.write("Análisis técnico de rendimiento y eventos detectados.")

with col_reglas:
    with st.expander("🔍 Reglas de Validación", expanded=True):
        st.markdown("""
        1. **Filtro de Movimiento:** Velocidad = 0 y Odómetro sin cambios.
        2. **Anti-Oleaje:** Espera de 3 min tras detenerse para estabilizar lectura.
        3. **Umbrales:** Robos > 4L | Cargas > 15L.
        """)

file = st.file_uploader("Subir archivo CSV", type=['csv'])

if file:
    try:
        df_raw = pd.read_csv(file)
        resumen, eventos = analizar_datos_pro(df_raw)
        
        st.subheader("📊 Balance General")
        # Mostrar métricas con sus fórmulas debajo
        cols = st.columns(len(resumen))
        for i, item in enumerate(resumen):
            with cols[i]:
                st.metric(label=item["label"], value=item["valor"])
                st.caption(f"fx: {item['formula']}")
        
        st.subheader("🚩 Ventanas Detalladas (PI / PF)")
        if not eventos.empty:
            st.table(eventos.sort_values('PI'))
        else:
            st.info("No se detectaron anomalías.")
            
    except Exception as e:
        st.error(f"Error: {e}")
