import streamlit as st
import pandas as pd
import numpy as np

# 1. CONFIGURACIÓN DE PÁGINA (Debe ser la primera instrucción de Streamlit)
st.set_page_config(page_title="Auditoría de Combustible v1.5", layout="wide")

def analizar_datos_pro(df, params):
    # Limpieza básica de cabeceras y fechas
    df.columns = df.columns.str.strip()
    df['Fecha Hora'] = pd.to_datetime(df['Fecha Hora'], dayfirst=True, errors='coerce')
    df = df.dropna(subset=['Fecha Hora']).sort_values('Fecha Hora')
    
    eventos_combinados = []
    i = 0
    total_filas = len(df)
    
    while i < total_filas:
        # --- ESTADO: VEHÍCULO EN PARADA  ---
        # Condición: Velocidad <= umbral e incremento de odómetro <= margen [cite: 1, 3]
        dist_odo = 0 if i == 0 else abs(df.iloc[i]['Odometro'] - df.iloc[i-1]['Odometro'])
        
        if df.iloc[i]['Velocidad'] <= params['v_parada'] and dist_odo <= params['odo_parada']:
            idx_inicio = i
            f_inicio = df.iloc[i]
            
            # Gestión de Ruido (Filtro de 2L) 
            # Si al iniciar la parada el combustible varía +-2.0L, el PI se desplaza [cite: 1, 2]
            proximo_idx = i + 1
            if proximo_idx < total_filas:
                f_siguiente = df.iloc[proximo_idx]
                var_inicial = abs(f_siguiente['Total combustible'] - f_inicio['Total combustible'])
                if var_inicial <= params['filtro_ruido']:
                    f_inicio = f_siguiente
                    idx_inicio = proximo_idx

            # Criterio de Permanencia y Validación de Cambio de Estado [cite: 3, 11]
            j = idx_inicio + 1
            while j < total_filas:
                f_act = df.iloc[j]
                # Regla de Histéresis: No procesar cambio instantáneo [cite: 10, 11]
                if f_act['Velocidad'] > params['v_parada']:
                    # Requiere persistencia de registros o salto de odo > 100m [cite: 12]
                    registros_futuros = df.iloc[j : j + params['persistencia_mov']]
                    if (registros_futuros['Velocidad'] > params['v_parada']).all() or \
                       (registros_futuros['Odometro'].max() - f_act['Odometro']) > 100:
                        break
                j += 1
            
            f_final = df.iloc[j-1] # Criterio de Cierre: Último registro con velocidad cero [cite: 4]
            diff_neta = round(f_final['Total combustible'] - f_inicio['Total combustible'], 2)

            # Clasificación por Umbrales (Regla de 10L) [cite: 18, 19]
            # Variaciones entre -10L y +10L entran en Zona de Silencio [cite: 20]
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
                    'L. Inicial': f_inicio['Total combustible'],
                    'L. Final': f_final['Total combustible']
                })
            i = j

        # --- ESTADO: VEHÍCULO EN MOVIMIENTO [cite: 6] ---
        else:
            # Regla de Continuidad: Inicio es el último registro de parada anterior [cite: 7]
            idx_inicio_mov = i - 1 if i > 0 else i 
            f_inicio_mov = df.iloc[idx_inicio_mov]
            
            j = i + 1
            while j < total_filas:
                # Histéresis de Cierre: Requiere N registros en 0 para cerrar ventana [cite: 16, 17]
                if (df.iloc[j : j + params['histeresis_cierre']]['Velocidad'] <= params['v_parada']).all():
                    break
                j += 1
            
            f_final_mov = df.iloc[min(j, total_filas-1)]
            distancia_tramo = (f_final_mov['Odometro'] - f_inicio_mov['Odometro']) / 1000
            consumo_tramo = f_inicio_mov['Total combustible'] - f_final_mov['Total combustible']
            
            if distancia_tramo > 0.1 and consumo_tramo > 0:
                rendimiento_tramo = distancia_tramo / consumo_tramo
                # Anomalía Crítica [cite: 22, 23]
                if rendimiento_tramo < params['rendimiento_critico']:
                    eventos_combinados.append({
                        'Fecha Inicio': f_inicio_mov['Fecha Hora'],
                        'Fecha Fin': f_final_mov['Fecha Hora'],
                        'Tipo': 'ANOMALÍA MOVIMIENTO',
                        'Detalle': f"{round(rendimiento_tramo, 2)} km/L",
                        'Distancia (Km)': round(distancia_tramo, 2),
                        'L. Inicial': f_inicio_mov['Total combustible'],
                        'L. Final': f_final_mov['Total combustible']
                    })
            i = j

    return pd.DataFrame(eventos_combinados), df

# --- 2. INTERFAZ DE USUARIO Y PARÁMETROS EDITABLES ---
st.title("📋 Auditoría de Combustible v1.5")

with st.expander("⚙️ Configuración de Reglas Lógicas (Histéresis y Umbrales)", expanded=True):
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        v_parada = st.number_input("Velocidad Parada (km/h)", 0.0, 5.0, 2.0)
        histeresis_cierre = st.number_input("Registros Cierre Mov.", 1, 5, 2) # [cite: 17]
    with c2:
        umbral_carga = st.number_input("Umbral Carga (L)", 1.0, 50.0, 10.0) # [cite: 18]
        umbral_robo = st.number_input("Umbral Robo (L)", -50.0, -1.0, -10.0) # [cite: 19]
    with c3:
        filtro_ruido = st.number_input("Filtro Oleaje (L)", 0.5, 5.0, 2.0) # 
        rendimiento_critico = st.number_input("Rend. Crítico (km/L)", 0.1, 5.0, 0.5) # [cite: 22]
    with c4:
        persistencia_mov = st.number_input("Persistencia Mov. (Registros)", 1, 5, 2) # [cite: 12]
        odo_parada = st.number_input("Margen Odo Parada (m)", 0, 50, 10) # 

params = {
    'v_parada': v_parada, 'histeresis_cierre': histeresis_cierre,
    'umbral_carga': umbral_carga, 'umbral_robo': umbral_robo,
    'filtro_ruido': filtro_ruido, 'rendimiento_critico': rendimiento_critico,
    'persistencia_mov': persistencia_mov, 'odo_parada': odo_parada
}

# --- 3. PROCESAMIENTO DE ARCHIVO ---
file = st.file_uploader("Subir archivo de telemetría (CSV)", type=['csv'])

if file:
    try:
        df_raw = pd.read_csv(file)
        df_eventos, df_clean = analizar_datos_pro(df_raw, params)
        
        if not df_eventos.empty:
            # Tratamiento de Información y Consolidación [cite: 23]
            cargos = df_eventos[df_eventos['Tipo'] == 'CARGA']
            robos = df_eventos[df_eventos['Tipo'] == 'DESCARGA/ROBO']
            
            total_cargado = (cargos['L. Final'] - cargos['L. Inicial']).sum()
            total_robado = abs((robos['L. Final'] - robos['L. Inicial']).sum())
            
            c_ini, c_fin = df_clean['Total combustible'].iloc[0], df_clean['Total combustible'].iloc[-1]
            
            # Fórmulas de Consolidación [cite: 23, 24]
            consumo_real = round((c_ini + total_cargado) - c_fin, 2)
            consumo_neto = round(consumo_real - total_robado, 2)

            st.subheader("📊 Balance General")
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Cargas Totales", f"{total_cargado:.2f} L")
            m2.metric("Robos Totales", f"{total_robado:.2f} L")
            m3.metric("Consumo Real", f"{consumo_real:.2f} L")
            m4.metric("Consumo Neto (Op.)", f"{consumo_neto:.2f} L")

            st.subheader("🚩 Línea de Tiempo de Eventos")
            st.dataframe(df_eventos, use_container_width=True)
        else:
            st.info("No se detectaron eventos con los parámetros actuales.")
            
    except Exception as e:
        st.error(f"Error técnico en el procesamiento: {e}")
