import streamlit as st
import pandas as pd
import numpy as np

# --- 1. CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Reporte de Combustible v1.5", layout="wide")

# --- 2. FUNCIONES DE PROCESAMIENTO ---
def analizar_datos_pro(df, params):
    # Limpieza y Formato
    df.columns = df.columns.str.strip()
    df['Fecha Hora'] = pd.to_datetime(df['Fecha Hora'], dayfirst=True, errors='coerce')
    df = df.dropna(subset=['Fecha Hora']).sort_values('Fecha Hora')
    
    eventos_combinados = []
    i = 0
    total_filas = len(df)
    
    while i < total_filas:
        # --- ESTADO: VEHÍCULO EN PARADA ---
        dist_odo = 0 if i == 0 else abs(df.iloc[i]['Odometro'] - df.iloc[i-1]['Odometro'])
        
        if df.iloc[i]['Velocidad'] <= params['v_parada'] and dist_odo <= params['odo_parada']:
            idx_inicio = i
            f_inicio = df.iloc[i]
            
            # Gestión de Ruido (Filtro de 2L) [cite: 1, 2]
            proximo_idx = i + 1
            if proximo_idx < total_filas:
                f_siguiente = df.iloc[proximo_idx]
                var_inicial = abs(f_siguiente['Total combustible'] - f_inicio['Total combustible'])
                if var_inicial <= params['filtro_ruido']:
                    f_inicio = f_siguiente
                    idx_inicio = proximo_idx

            # Criterio de Permanencia e Histéresis de Cambio [cite: 3, 12]
            j = idx_inicio + 1
            while j < total_filas:
                f_act = df.iloc[j]
                if f_act['Velocidad'] > params['v_parada']:
                    # Validación de persistencia para confirmar movimiento [cite: 12]
                    registros_futuros = df.iloc[j : j + params['persistencia_mov']]
                    if (registros_futuros['Velocidad'] > params['v_parada']).all() or \
                       (registros_futuros['Odometro'].max() - f_act['Odometro']) > 100:
                        break
                j += 1
            
            f_final = df.iloc[j-1]
            diff_neta = round(f_final['Total combustible'] - f_inicio['Total combustible'], 2)

            # Clasificación de Eventos (Regla de 10L) [cite: 18, 19]
            if diff_neta >= params['umbral_carga']:
                tipo = "CARGA"
            elif diff_neta <= params['umbral_robo']:
                tipo = "DESCARGA/ROBO"
            else:
                tipo = None

            if tipo:
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
            # Regla de Continuidad [cite: 7]
            idx_inicio_mov = i - 1 if i > 0 else i 
            f_inicio_mov = df.iloc[idx_inicio_mov]
            
            j = i + 1
            while j < total_filas:
                # Histéresis de Cierre [cite: 17]
                if (df.iloc[j : j + params['histeresis_cierre']]['Velocidad'] <= params['v_parada']).all():
                    break
                j += 1
            
            f_final_mov = df.iloc[min(j, total_filas-1)]
            distancia_tramo = (f_final_mov['Odometro'] - f_inicio_mov['Odometro']) / 1000
            consumo_tramo = f_inicio_mov['Total combustible'] - f_final_mov['Total combustible']
            
            if distancia_tramo > 0.1 and consumo_tramo > 0:
                rendimiento_tramo = distancia_tramo / consumo_tramo
                # Anomalía Crítica [cite: 22]
                if rendimiento_tramo < params['rendimiento_critico']:
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

    return pd.DataFrame(eventos_combinados), df

def style_tipo(row):
    color = ''
    if row['Tipo'] == 'CARGA': color = 'background-color: #d4edda; color: #155724' 
    elif row['Tipo'] == 'DESCARGA/ROBO': color = 'background-color: #f8d7da; color: #721c24' 
    elif row['Tipo'] == 'ANOMALÍA MOVIMIENTO': color = 'background-color: #fff3cd; color: #856404' 
    return [color] * len(row)

# --- 3. INTERFAZ DE USUARIO ---
st.title("📋 Reporte de Combustible y Auditoría")

# Fila de Parámetros Editables
with st.expander("⚙️ Configuración de Reglas Lógicas", expanded=True):
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        v_parada = st.number_input("Velocidad Parada (km/h)", 0.0, 5.0, 2.0)
        histeresis_cierre = st.number_input("Registros Cierre Mov.", 1, 5, 2)
    with c2:
        umbral_carga = st.number_input("Umbral Carga (L)", 1.0, 50.0, 10.0)
        umbral_robo = st.number_input("Umbral Robo (L)", -50.0, -1.0, -10.0)
    with c3:
        filtro_ruido = st.number_input("Filtro Oleaje (L)", 0.5, 5.0, 2.0)
        rendimiento_critico = st.number_input("Rend. Crítico (km/L)", 0.1, 5.0, 0.5)
    with c4:
        persistencia_mov = st.number_input("Persistencia Mov. (Reg)", 1, 5, 2)
        odo_parada = st.number_input("Margen Odo (m)", 0, 50, 10)

params = {
    'v_parada': v_parada, 'histeresis_cierre': histeresis_cierre,
    'umbral_carga': umbral_carga, 'umbral_robo': umbral_robo,
    'filtro_ruido': filtro_ruido, 'rendimiento_critico': rendimiento_critico,
    'persistencia_mov': persistencia_mov, 'odo_parada': odo_parada
}

file = st.file_uploader("Subir archivo de telemetría (CSV)", type=['csv'])

if file:
    try:
        df_raw = pd.read_csv(file)
        df_eventos, df_clean = analizar_datos_pro(df_raw, params)
        
        if not df_eventos.empty:
            # Consolidación [cite: 23, 24]
            cargos = df_eventos[df_eventos['Tipo'] == 'CARGA']
            robos = df_eventos[df_eventos['Tipo'] == 'DESCARGA/ROBO']
            
            t_cargas = (cargos['L. Final'] - cargos['L. Inicial']).sum()
            t_robos = abs((robos['L. Final'] - robos['L. Inicial']).sum())
            
            c_ini, c_fin = df_clean['Total combustible'].iloc[0], df_clean['Total combustible'].iloc[-1]
            dist_total = (df_clean['Odometro'].max() - df_clean['Odometro'].min()) / 1000
            
            consumo_real = round((c_ini + t_cargas) - c_fin, 2)
            consumo_neto = round(consumo_real - t_robos, 2)
            rend_neto = round(dist_total / consumo_neto, 2) if consumo_neto > 0 else 0

            # Balance General con Métricas
            st.subheader("📊 Balance General")
            m1, m2, m3, m4, m5 = st.columns(5)
            m1.metric("Distancia", f"{dist_total:.2f} Km")
            m2.metric("Total Cargado", f"{t_cargas:.2f} L")
            m3.metric("Total Robado", f"{t_robos:.2f} L")
            m4.metric("Consumo Real", f"{consumo_real:.2f} L")
            m5.metric("Rend. Neto", f"{rend_neto} Km/L")

            # Tabla Estilizada
            st.subheader("🚩 Línea de Tiempo de Eventos")
            df_display = df_eventos.sort_values('Fecha Inicio')
            st.table(df_display.style.apply(style_tipo, axis=1))
        else:
            st.info("No se detectaron eventos con los parámetros configurados.")
            
    except Exception as e:
        st.error(f"Error en el procesamiento: {e}")
