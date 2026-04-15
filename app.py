import streamlit as st
import pandas as pd
import numpy as np

def analizar_datos_pro(df):
    # 1. Limpieza y Formato
    df.columns = df.columns.str.strip()
    df['Fecha Hora'] = pd.to_datetime(df['Fecha Hora'], dayfirst=True, errors='coerce')
    df = df.dropna(subset=['Fecha Hora']).sort_values('Fecha Hora')
    
    # --- PARÁMETROS DE AUDITORÍA (Condicionales) ---
    UMBRAL_EVENTO = 10.0        # Solo eventos >= 10L (Carga o Robo)
    UMBRAL_RUIDO_INICIAL = 2.0  # Ignorar variaciones < 2L al inicio de parada
    RENDIMIENTO_MINIMO = 1.2    # Alerta movimiento si rinde < 1.2 km/L
    
    eventos_combinados = []
    i = 0
    total_filas = len(df)
    
    while i < total_filas:
        # --- CASO A: ANÁLISIS EN PARADA (Velocidad 0) ---
        if df.iloc[i]['Velocidad'] == 0:
            idx_inicio = i
            f_inicio = df.iloc[i]
            
            # Regla de Continuidad: Filtro de ruido inicial
            proximo_idx = i + 1
            if proximo_idx < total_filas:
                f_siguiente = df.iloc[proximo_idx]
                salto_inmediato = f_siguiente['Total combustible'] - f_inicio['Total combustible']
                if 0 < salto_inmediato < UMBRAL_RUIDO_INICIAL:
                    f_inicio = f_siguiente
                    idx_inicio = proximo_idx

            # Buscar fin de parada
            j = idx_inicio + 1
            while j < total_filas:
                f_act = df.iloc[j]
                odo_diff = abs(f_act['Odometro'] - df.iloc[j-1]['Odometro'])
                if f_act['Velocidad'] > 2 or odo_diff > 1:
                    break
                j += 1
            
            f_final = df.iloc[j-1]
            diff_neta = round(f_final['Total combustible'] - f_inicio['Total combustible'], 2)

            # Lógica de Validación de Evento
            if abs(diff_neta) >= UMBRAL_EVENTO:
                tipo = "CARGA" if diff_neta > 0 else "DESCARGA/ROBO"
                eventos_combinados.append({
                    'Fecha Inicio': f_inicio['Fecha Hora'],
                    'Fecha Fin': f_final['Fecha Hora'],
                    'Tipo': tipo,
                    'Detalle': f"{diff_neta} L (Balance en parada)",
                    'Km/L': "N/A",
                    'Distancia (Km)': 0,
                    'L. Inicial': f_inicio['Total combustible'],
                    'L. Final': f_final['Total combustible']
                })
            i = j

        # --- CASO B: ANÁLISIS EN MOVIMIENTO (Velocidad > 0) ---
        else:
            # Incluye el último punto de la parada para capturar la caída inicial
            idx_inicio_mov = i - 1 if i > 0 else i 
            f_inicio_mov = df.iloc[idx_inicio_mov]
            
            j = i + 1
            while j < total_filas:
                if df.iloc[j]['Velocidad'] == 0:
                    break
                j += 1
            
            f_final_mov = df.iloc[j-1]
            distancia_tramo = (f_final_mov['Odometro'] - f_inicio_mov['Odometro']) / 1000
            consumo_tramo = f_inicio_mov['Total combustible'] - f_final_mov['Total combustible']
            
            if distancia_tramo > 0.1 and consumo_tramo > 0:
                rendimiento_tramo = distancia_tramo / consumo_tramo
                # Condicional de rendimiento anómalo
                if rendimiento_tramo < RENDIMIENTO_MINIMO:
                    eventos_combinados.append({
                        'Fecha Inicio': f_inicio_mov['Fecha Hora'],
                        'Fecha Fin': f_final_mov['Fecha Hora'],
                        'Tipo': 'ANOMALÍA MOVIMIENTO',
                        'Detalle': f"Gasto: {round(consumo_tramo,2)} L en {round(distancia_tramo,2)} Km",
                        'Km/L': round(rendimiento_tramo, 2),
                        'Distancia (Km)': round(distancia_tramo, 2),
                        'L. Inicial': f_inicio_mov['Total combustible'],
                        'L. Final': f_final_mov['Total combustible']
                    })
            i = j

    # --- CÁLCULOS BALANCE FINAL ---
    dist_total = (df['Odometro'].max() - df['Odometro'].min()) / 1000
    comb_i, comb_f = df['Total combustible'].iloc[0], df['Total combustible'].iloc[-1]
    
    df_res = pd.DataFrame(eventos_combinados)
    total_cargado = 0
    total_robado = 0
    
    if not df_res.empty:
        total_cargado = df_res[df_res['Tipo'] == 'CARGA'].apply(lambda x: x['L. Final'] - x['L. Inicial'], axis=1).sum()
        total_robado = abs(df_res[df_res['Tipo'] == 'DESCARGA/ROBO'].apply(lambda x: x['L. Final'] - x['L. Inicial'], axis=1).sum())

    consumo_real = round((comb_i + total_cargado) - comb_f, 2)
    consumo_neto = round(consumo_real - total_robado, 2)

    resumen_visual = [
        {"label": "Distancia (Km)", "valor": f"{dist_total:,.2f}"},
        {"label": "Total Cargado (L)", "valor": f"{total_cargado:,.2f}"},
        {"label": "Total Robado (L)", "valor": f"{total_robado:,.2f}"},
        {"label": "Consumo Real (L)", "valor": f"{consumo_real:,.2f}"},
        {"label": "Rend. Neto", "valor": f"{round(dist_total/consumo_neto, 2) if consumo_neto > 0 else 0} km/l"}
    ]
    
    return resumen_visual, df_res

def style_tipo(row):
    color = ''
    if row['Tipo'] == 'CARGA': color = 'background-color: #d4edda; color: #155724' 
    elif row['Tipo'] == 'DESCARGA/ROBO': color = 'background-color: #f8d7da; color: #721c24' 
    elif row['Tipo'] == 'ANOMALÍA MOVIMIENTO': color = 'background-color: #fff3cd; color: #856404' 
    return [color] * len(row)

# --- INTERFAZ STREAMLIT ---
st.set_page_config(page_title="Reporte de Combustible", layout="wide")

col_titulo, col_reglas = st.columns([1.8, 1.2])

with col_titulo:
    st.title("📋 Reporte de Combustible")
    st.write("Análisis técnico de balance de energía y auditoría de eventos.")

with col_reglas:
    with st.expander("🔍 Reglas de Validación y Condicionales", expanded=True):
        st.markdown(f"""
        **En Parada (Velocidad = 0):**
        * **Umbral de Evento:** Solo se registran CARGAS o ROBOS si la variación neta es **≥ 10.0 L**.
        * **Filtro de Ruido:** Si el combustible sube < 2L al detenerse, el punto de inicio se desplaza para ignorar el oleaje.
        * **Balance Neto:** Se calcula comparando el nivel exacto al llegar vs. el nivel al salir de la parada.

        **En Movimiento (Velocidad > 0):**
        * **Rendimiento Mínimo:** Se activa la alerta si el rendimiento del tramo es **< 1.2 km/L**.
        * **Ventana de Análisis:** Incluye el diferencial de combustible desde el último segundo de la parada hasta que se detiene de nuevo.
        """)

file = st.file_uploader("Subir archivo CSV", type=['csv'])

if file:
    try:
        df_raw = pd.read_csv(file)
        resumen, df_eventos = analizar_datos_pro(df_raw)
        
        st.subheader("📊 Balance General")
        cols = st.columns(len(resumen))
        for i, item in enumerate(resumen):
            cols[i].metric(label=item["label"], value=item["valor"])
        
        st.subheader("🚩 Línea de Tiempo de Anomalías y Cargas")
        if not df_eventos.empty:
            df_eventos = df_eventos.sort_values('Fecha Inicio')
            st.table(df_eventos.style.apply(style_tipo, axis=1))
        else:
            st.info("No se detectaron eventos (Cargas/Robos ≥ 10L o Rendimientos < 1.2 km/L).")
            
    except Exception as e:
        st.error(f"Error en el proceso: {e}")
