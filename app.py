import streamlit as st
import pandas as pd
import numpy as np

def analizar_datos_pro(df):
    df.columns = df.columns.str.strip()
    df['Fecha Hora'] = pd.to_datetime(df['Fecha Hora'], dayfirst=True, errors='coerce')
    df = df.dropna(subset=['Fecha Hora']).sort_values('Fecha Hora')
    
    # --- Parámetros de Auditoría Sensible ---
    UMBRAL_ROBO_ACUMULADO = -3.0 # Si en un periodo parado pierde > 3L, es robo
    MINUTOS_ESTABILIZACION = 1   # Reducido para no ignorar inicios de robo
    
    eventos = []
    i = 0
    
    while i < len(df) - 1:
        f_inicio = df.iloc[i]
        odo_cambio = abs(df.iloc[i]['Odometro'] - df.iloc[i-1]['Odometro']) if i > 0 else 0
        
        # Si el camión está estático (Velocidad 0 y Odo quieto)
        if f_inicio['Velocidad'] == 0 and odo_cambio <= 1:
            inicio_ventana = f_inicio['Fecha Hora']
            comb_inicial_ventana = f_inicio['Total combustible']
            
            k = i + 1
            while k < len(df):
                f_actual = df.iloc[k]
                odo_k = abs(f_actual['Odometro'] - df.iloc[k-1]['Odometro'])
                
                # Si se mueve, cerramos la ventana de análisis estático
                if f_actual['Velocidad'] > 2 or odo_k > 1:
                    break
                
                # Calculamos la diferencia neta desde que se detuvo
                diff_neta = f_actual['Total combustible'] - comb_inicial_ventana
                
                # DETECCIÓN DE ROBO (Incluso con incrementos/decrementos simultáneos)
                if diff_neta <= UMBRAL_ROBO_ACUMULADO:
                    # Buscamos hasta que el nivel deje de bajar o el camión se mueva
                    m = k
                    while m < len(df) - 1:
                        f_sig = df.iloc[m+1]
                        if f_sig['Velocidad'] > 2 or (f_sig['Total combustible'] > f_actual['Total combustible'] + 1): # +1L de margen ruido
                            break
                        f_actual = f_sig
                        m += 1
                    
                    eventos.append({
                        'Tipo': 'DESCARGA/ROBO',
                        'PI': inicio_ventana,
                        'PF': f_actual['Fecha Hora'],
                        'Litros': round(f_actual['Total combustible'] - comb_inicial_ventana, 2),
                        'Odo': f_actual['Odometro']
                    })
                    k = m # Saltamos al final del evento
                    break
                
                # DETECCIÓN DE CARGA
                elif diff_neta >= 15.0:
                    eventos.append({
                        'Tipo': 'CARGA',
                        'PI': inicio_ventana,
                        'PF': f_actual['Fecha Hora'],
                        'Litros': round(diff_neta, 2),
                        'Odo': f_actual['Odometro']
                    })
                    break
                k += 1
            i = k
        else:
            i += 1

    # --- BALANCE Y CÁLCULOS ---
    dist_i, dist_f = df['Odometro'].min(), df['Odometro'].max()
    distancia_total = (dist_f - dist_i) / 1000
    comb_i, comb_f = df['Total combustible'].iloc[0], df['Total combustible'].iloc[-1]
    
    df_ev = pd.DataFrame(eventos)
    total_cargado = df_ev[df_ev['Tipo'] == 'CARGA']['Litros'].sum() if not df_ev.empty else 0
    total_robado = abs(df_ev[df_ev['Tipo'] == 'DESCARGA/ROBO']['Litros'].sum()) if not df_ev.empty else 0
    
    consumo_real = round((comb_i + total_cargado) - comb_f, 2)
    consumo_neto = round(consumo_real - total_robado, 2)

    resumen_visual = [
        {"label": "Distancia (Km)", "valor": f"{distancia_total:,.2f}", "formula": "Odo Final - Odo Inicial"},
        {"label": "Cargado (L)", "valor": f"{total_cargado:,.2f}", "formula": "Suma de eventos > 15L"},
        {"label": "Robado (L)", "valor": f"{total_robado:,.2f}", "formula": "Diferencia neta en parada"},
        {"label": "Consumo Real (L)", "valor": f"{consumo_real:,.2f}", "formula": "(Ini + Cargas) - Final"},
        {"label": "Rend. Bruto", "valor": f"{round(distancia_total/consumo_real,2) if consumo_real > 0 else 0} km/l", "formula": "Km / Consumo Real"},
        {"label": "Rend. Neto", "valor": f"{round(distancia_total/consumo_neto,2) if consumo_neto > 0 else 0} km/l", "formula": "Km / (Consumo Real - Robos)"}
    ]
    
    return resumen_visual, df_ev

# --- INTERFAZ ---
st.set_page_config(page_title="Reporte de Combustible", layout="wide")

col_titulo, col_reglas = st.columns([2, 1])
with col_titulo:
    st.title("📋 Reporte de Combustible")
    st.write("Detección avanzada de extracciones y balance de masa.")

with col_reglas:
    with st.expander("🔍 Reglas de Validación", expanded=True):
        st.markdown("""
        1. **Filtro Estático:** Solo se analiza si Velocidad = 0 y el Odómetro no cambia.
        2. **Diferencia Neta:** Se mide la pérdida acumulada desde el minuto 1 de la detención.
        3. **Umbral de Robo:** Cualquier caída neta > 3L en estado estático se registra como evento.
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
        
        st.subheader("🚩 Ventanas Detalladas (PI / PF)")
        if not eventos.empty:
            st.table(eventos.sort_values('PI'))
        else:
            st.info("No se detectaron anomalías con los parámetros actuales.")
    except Exception as e:
        st.error(f"Error: {e}")
