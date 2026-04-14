import streamlit as st
import pandas as pd
import numpy as np

def analizar_datos_pro(df):
    # 1. Limpieza y Formato
    df.columns = df.columns.str.strip()
    df['Fecha Hora'] = pd.to_datetime(df['Fecha Hora'], dayfirst=True, errors='coerce')
    df = df.dropna(subset=['Fecha Hora']).sort_values('Fecha Hora')
    
    # --- Parámetros de Auditoría ---
    UMBRAL_ROBO = -5.0  
    UMBRAL_CARGA = 15.0 
    MINUTOS_ESTABILIZACION = 3 
    
    eventos = []
    i = 0
    
    while i < len(df) - 1:
        f_inicio = df.iloc[i]
        
        # Validación de Odómetro estático (Tolerancia 1 metro)
        odo_cambio = abs(df.iloc[i]['Odometro'] - df.iloc[i-1]['Odometro']) if i > 0 else 0
        
        if f_inicio['Velocidad'] == 0 and odo_cambio <= 1:
            # Ventana de Estabilización tras detención (Evita falsos por oleaje/slosh)
            hora_estabilizada = f_inicio['Fecha Hora'] + pd.Timedelta(minutes=MINUTOS_ESTABILIZACION)
            
            j = i
            while j < len(df) - 1 and df.iloc[j]['Fecha Hora'] < hora_estabilizada:
                j += 1
            
            if j >= len(df) - 1: break
            
            f_estable = df.iloc[j]
            k = j + 1
            while k < len(df):
                f_actual = df.iloc[k]
                
                # Si detecta movimiento real, se cierra la ventana de auditoría
                cambio_odo_k = abs(f_actual['Odometro'] - df.iloc[k-1]['Odometro'])
                if f_actual['Velocidad'] > 2 or cambio_odo_k > 1:
                    break
                
                diff_acumulada = f_actual['Total combustible'] - f_estable['Total combustible']
                
                if diff_acumulada <= UMBRAL_ROBO:
                    while k < len(df)-1 and df.iloc[k+1]['Total combustible'] <= f_actual['Total combustible'] and df.iloc[k+1]['Velocidad'] == 0:
                        k += 1
                        f_actual = df.iloc[k]
                    
                    eventos.append({
                        'Tipo': 'DESCARGA/ROBO',
                        'PI': f_estable['Fecha Hora'],
                        'PF': f_actual['Fecha Hora'],
                        'Litros': round(f_actual['Total combustible'] - f_estable['Total combustible'], 2),
                        'Odo': f_actual['Odometro']
                    })
                    break

                elif diff_acumulada >= UMBRAL_CARGA:
                    while k < len(df)-1 and df.iloc[k+1]['Total combustible'] >= f_actual['Total combustible'] and df.iloc[k+1]['Velocidad'] == 0:
                        k += 1
                        f_actual = df.iloc[k]
                        
                    eventos.append({
                        'Tipo': 'CARGA',
                        'PI': f_estable['Fecha Hora'],
                        'PF': f_actual['Fecha Hora'],
                        'Litros': round(f_actual['Total combustible'] - f_estable['Total combustible'], 2),
                        'Odo': f_actual['Odometro']
                    })
                    break
                k += 1
            i = k
        else:
            i += 1

    # --- CÁLCULOS FINALES ---
    distancia_total = (df['Odometro'].max() - df['Odometro'].min()) / 1000
    comb_inicial = df['Total combustible'].iloc[0]
    comb_final = df['Total combustible'].iloc[-1]
    
    df_ev = pd.DataFrame(eventos)
    total_cargado = df_ev[df_ev['Tipo'] == 'CARGA']['Litros'].sum() if not df_ev.empty else 0
    total_robado = abs(df_ev[df_ev['Tipo'] == 'DESCARGA/ROBO']['Litros'].sum()) if not df_ev.empty else 0
    
    consumo_total_real = round((comb_inicial + total_cargado) - comb_final, 2)
    consumo_motor_neto = round(consumo_total_real - total_robado, 2)
    
    resumen = {
        'Distancia (Km)': f"{distancia_total:,.2f}",
        'Inicial (L)': f"{comb_inicial:,.2f}",
        'Cargado (L)': f"{total_cargado:,.2f}",
        'Robado (L)': f"{total_robado:,.2f}",
        'Rend. Bruto': f"{round(distancia_total/consumo_total_real,2) if consumo_total_real > 0 else 0} km/l",
        'Rend. Neto': f"{round(distancia_total/consumo_motor_neto,2) if consumo_motor_neto > 0 else 0} km/l"
    }
    
    return resumen, df_ev

# --- INTERFAZ ---
st.set_page_config(page_title="Reporte de Combustible", layout="wide")

# Encabezado con Reglas de Validación a la derecha
col_titulo, col_reglas = st.columns([2, 1])

with col_titulo:
    st.title("📋 Reporte de Combustible")
    st.write("Análisis de eficiencia y eventos de telemetría.")

with col_reglas:
    with st.expander("🔍 Reglas de Validación", expanded=True):
        st.markdown("""
        1. **Filtro de Movimiento:** No se auditan cambios si el odómetro varía o la velocidad es > 2 km/h.
        2. **Anti-Oleaje:** Se ignoran los primeros 3 minutos tras detenerse para esperar estabilidad del líquido.
        3. **Umbral de Robo:** Solo se registran descargas estáticas mayores a 5 litros.
        4. **Umbral de Carga:** Solo se registran incrementos mayores a 15 litros.
        """)

file = st.file_uploader("Subir archivo CSV de telemetría", type=['csv'])

if file:
    try:
        df_raw = pd.read_csv(file)
        resumen, eventos = analizar_datos_pro(df_raw)
        
        st.subheader("📊 Balance General")
        cols = st.columns(len(resumen))
        for i, (k, v) in enumerate(resumen.items()):
            cols[i].metric(k, v)
        
        st.subheader("🚩 Ventanas Detalladas (PI / PF)")
        if not eventos.empty:
            st.table(eventos.sort_values('PI'))
        else:
            st.info("No se detectaron anomalías significativas bajo las reglas actuales.")
            
    except Exception as e:
        st.error(f"Error en el procesamiento: {e}")
