import streamlit as st
import pandas as pd
import numpy as np

def analizar_datos_pro(df):
    # 1. Limpieza y Formato
    df.columns = df.columns.str.strip()
    df['Fecha Hora'] = pd.to_datetime(df['Fecha Hora'], dayfirst=True, errors='coerce')
    df = df.dropna(subset=['Fecha Hora']).sort_values('Fecha Hora')
    
    # --- PARÁMETROS TÉCNICOS Y REGLAS DE HISTÉRESIS ---
    UMBRAL_EVENTO = 10        # Regla de 10L para Cargas/Robos [cite: 18, 19]
    FILTRO_RUIDO = 2.0        # Filtro de 2L para oleaje 
    RENDIMIENTO_MINIMO = 0.5  # Anomalía Crítica < 0.5 km/L [cite: 22]
    PERSISTENCIA_MOV = 2      # Registros para confirmar movimiento 
    HISTERESIS_CIERRE = 2     # Registros en 0 para cerrar tramo [cite: 17]
    V_PARADA = 2              # Velocidad umbral parada 
    ODO_PARADA = 10           # Incremento odo máximo en parada 
    
    eventos_combinados = []
    i = 0
    total_filas = len(df)
    
    while i < total_filas:
        # --- ESTADO: VEHÍCULO EN PARADA ---
        dist_odo = 0 if i == 0 else abs(df.iloc[i]['Odometro'] - df.iloc[i-1]['Odometro'])
        if df.iloc[i]['Velocidad'] <= V_PARADA and dist_odo <= ODO_PARADA:
            idx_inicio = i
            f_inicio = df.iloc[i]
            
            # Gestión de Ruido (Filtro de 2L): Desplaza PI si hay oleaje [cite: 1, 2]
            proximo_idx = i + 1
            if proximo_idx < total_filas:
                f_siguiente = df.iloc[proximo_idx]
                var_inicial = abs(f_siguiente['Total combustible'] - f_inicio['Total combustible'])
                if var_inicial <= FILTRO_RUIDO:
                    f_inicio = f_siguiente
                    idx_inicio = proximo_idx

            # Criterio de Permanencia y Validación de Cambio de Estado [cite: 11]
            j = idx_inicio + 1
            while j < total_filas:
                f_act = df.iloc[j]
                # Validación de Persistencia: Confirmar si sale de la parada 
                if f_act['Velocidad'] > V_PARADA:
                    registros_futuros = df.iloc[j : j + PERSISTENCIA_MOV]
                    # Si no hay persistencia, se considera "Registro Fugaz" y se absorbe [cite: 13, 14]
                    if (registros_futuros['Velocidad'] > V_PARADA).all() or \
                       (registros_futuros['Odometro'].max() - f_act['Odometro']) > 100:
                        break
                j += 1
            
            f_final = df.iloc[j-1]
            diff_neta = round(f_final['Total combustible'] - f_inicio['Total combustible'], 2)

            # Clasificación por Umbrales [cite: 18, 19, 20]
            if abs(diff_neta) >= UMBRAL_EVENTO:
                tipo = "CARGA" if diff_neta > 0 else "DESCARGA/ROBO"
                eventos_combinados.append({
                    'Fecha Inicio': f_inicio['Fecha Hora'],
                    'Fecha Fin': f_final['Fecha Hora'],
                    'Tipo': tipo,
                    'Detalle': f"{diff_neta} L",
                    'Km/L': "N/A",
                    'Distancia (Km)': 0,
                    'L. Inicial': f_inicio['Total combustible'],
                    'L. Final': f_final['Total combustible']
                })
            i = j

        # --- ESTADO: VEHÍCULO EN MOVIMIENTO ---
        else:
            # Regla de Continuidad: Inicia en el último punto de la parada [cite: 7]
            idx_inicio_mov = i - 1 if i > 0 else i 
            f_inicio_mov = df.iloc[idx_inicio_mov]
            
            j = i + 1
            while j < total_filas:
                # Histéresis de Cierre: Evita cierres prematuros en semáforos 
                if (df.iloc[j : j + HISTERESIS_CIERRE]['Velocidad'] <= V_PARADA).all():
                    break
                j += 1
            
            f_final_mov = df.iloc[min(j, total_filas-1)]
            distancia_tramo = (f_final_mov['Odometro'] - f_inicio_mov['Odometro']) / 1000
            consumo_tramo = f_inicio_mov['Total combustible'] - f_final_mov['Total combustible']
            
            if distancia_tramo > 0.1 and consumo_tramo > 0:
                rendimiento_tramo = distancia_tramo / consumo_tramo
                # Anomalía Crítica [cite: 22, 23]
                if rendimiento_tramo < RENDIMIENTO_MINIMO:
                    eventos_combinados.append({
                        'Fecha Inicio': f_inicio_mov['Fecha Hora'],
                        'Fecha Fin': f_final_mov['Fecha Hora'],
                        'Tipo': 'ANOMALÍA MOVIMIENTO',
                        'Detalle': f"{round(rendimiento_tramo, 2)} km/L",
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
        # Consolidación según fórmulas del documento [cite: 24]
        total_cargado = df_res[df_res['Tipo'] == 'CARGA'].apply(lambda x: x['L. Final'] - x['L. Inicial'], axis=1).sum()
        total_robado = abs(df_res[df_res['Tipo'] == 'DESCARGA/ROBO'].apply(lambda x: x['L. Final'] - x['L. Inicial'], axis=1).sum())

    consumo_real = round((comb_i + total_cargado) - comb_f, 2)
    consumo_neto = round(consumo_real - total_robado, 2)
    rend_op = round(dist_total / consumo_neto, 2) if consumo_neto > 0 else 0

    resumen_visual = [
        {"label": "Distancia (Km)", "valor": f"{dist_total:,.2f}"},
        {"label": "Total Cargado (L)", "valor": f"{total_cargado:,.2f}"},
        {"label": "Total Robado (L)", "valor": f"{total_robado:,.2f}"},
        {"label": "Consumo Real (L)", "valor": f"{consumo_real:,.2f}"},
        {"label": "Rend. Neto", "valor": f"{rend_op} km/l"}
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
    st.write("Análisis técnico de balance de energía con reglas de histéresis.")

with col_reglas:
    with st.expander("🔍 Histéresis y Validación de Estado", expanded=True):
        st.markdown(f"""
        **Reglas de Persistencia:**
        * **Confirmación de Movimiento:** Requiere 2 registros consecutivos > 2 km/h para evitar fragmentación por GPS Drift.
        * **Histéresis de Cierre:** Las detenciones momentáneas se mantienen en la ventana de movimiento[cite: 17].
        * **Filtro de Ruido (2L):** Se ignora el oleaje inicial al detenerse para mayor precisión en cargas.
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
            st.info("No se detectaron eventos (Cargas/Robos ≥ 10L o Rendimientos Críticos).")
            
    except Exception as e:
        st.error(f"Error en el proceso: {e}")
