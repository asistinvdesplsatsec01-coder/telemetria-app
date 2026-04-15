import streamlit as st
import pandas as pd
import numpy as np

def analizar_datos_pro(df):
    # 1. Limpieza y Formato
    df.columns = df.columns.str.strip()
    df['Fecha Hora'] = pd.to_datetime(df['Fecha Hora'], dayfirst=True, errors='coerce')
    df = df.dropna(subset=['Fecha Hora']).sort_values('Fecha Hora')
    
    # --- Parámetros de Auditoría ---
    UMBRAL_ANOMALIA = 3.0       
    UMBRAL_RUIDO_INICIAL = 2.0  
    RENDIMIENTO_MINIMO_ALERTA = 1.2 # km/l (Si rinde menos de esto, es anomalía)
    
    eventos_detenido = []
    eventos_movimiento = []
    i = 0
    total_filas = len(df)
    
    while i < total_filas:
        # --- CASO A: VEHÍCULO DETENIDO (Lógica actual) ---
        if df.iloc[i]['Velocidad'] == 0:
            idx_inicio = i
            f_inicio = df.iloc[i]
            
            proximo_idx = i + 1
            if proximo_idx < total_filas:
                f_siguiente = df.iloc[proximo_idx]
                salto_inmediato = f_siguiente['Total combustible'] - f_inicio['Total combustible']
                if 0 < salto_inmediato < UMBRAL_RUIDO_INICIAL:
                    f_inicio = f_siguiente
                    idx_inicio = proximo_idx

            j = idx_inicio + 1
            while j < total_filas:
                f_act = df.iloc[j]
                odo_diff = abs(f_act['Odometro'] - df.iloc[j-1]['Odometro'])
                if f_act['Velocidad'] > 2 or odo_diff > 1:
                    break
                j += 1
            
            f_final = df.iloc[j-1]
            diff_neta = round(f_final['Total combustible'] - f_inicio['Total combustible'], 2)

            if abs(diff_neta) >= UMBRAL_ANOMALIA:
                tipo = "CARGA" if diff_neta > 0 else "DESCARGA/ROBO"
                eventos_detenido.append({
                    'Tipo': tipo, 'PI': f_inicio['Fecha Hora'], 'PF': f_final['Fecha Hora'],
                    'L. Inicial': f_inicio['Total combustible'], 'L. Final': f_final['Total combustible'],
                    'Diferencia (L)': diff_neta, 'Odo': f_final['Odometro']
                })
            i = j

        # --- CASO B: VEHÍCULO EN MOVIMIENTO (Nueva Lógica de Tramo) ---
        else:
            idx_inicio_mov = i
            f_inicio_mov = df.iloc[i]
            
            j = i + 1
            while j < total_filas:
                f_act = df.iloc[j]
                # Se detiene si Vel es 0 por más de un par de registros o el odo se clava
                if f_act['Velocidad'] == 0:
                    break
                j += 1
            
            f_final_mov = df.iloc[j-1]
            
            # Cálculos del tramo
            distancia_tramo = (f_final_mov['Odometro'] - f_inicio_mov['Odometro']) / 1000
            consumo_tramo = f_inicio_mov['Total combustible'] - f_final_mov['Total combustible']
            
            if distancia_tramo > 0.1 and consumo_tramo > 0:
                rendimiento_tramo = distancia_tramo / consumo_tramo
                
                # Si el rendimiento es absurdamente bajo, es un robo en movimiento o fuga
                if rendimiento_tramo < RENDIMIENTO_MINIMO_ALERTA:
                    eventos_movimiento.append({
                        'Tipo': 'RENDIMIENTO ANÓMALO',
                        'Inicio': f_inicio_mov['Fecha Hora'],
                        'Fin': f_final_mov['Fecha Hora'],
                        'Km Recorridos': round(distancia_tramo, 2),
                        'L. Consumidos': round(consumo_tramo, 2),
                        'Rendimiento (km/L)': round(rendimiento_tramo, 2),
                        'Odo Inicio': f_inicio_mov['Odometro'],
                        'Odo Fin': f_final_mov['Odometro']
                    })
            i = j

    # --- CÁLCULOS BALANCE GENERAL ---
    dist_total = (df['Odometro'].max() - df['Odometro'].min()) / 1000
    comb_i, comb_f = df['Total combustible'].iloc[0], df['Total combustible'].iloc[-1]
    
    df_det = pd.DataFrame(eventos_detenido)
    total_cargado = df_det[df_det['Diferencia (L)'] > 0]['Diferencia (L)'].sum() if not df_det.empty else 0
    total_robado = abs(df_det[df_det['Diferencia (L)'] < 0]['Diferencia (L)'].sum()) if not df_det.empty else 0
    
    consumo_real = round((comb_i + total_cargado) - comb_f, 2)
    consumo_neto = round(consumo_real - total_robado, 2)

    resumen_visual = [
        {"label": "Distancia (Km)", "valor": f"{dist_total:,.2f}", "formula": "Odo Final - Odo Inicial"},
        {"label": "Total Cargado (L)", "valor": f"{total_cargado:,.2f}", "formula": "Suma balances (+) en paradas"},
        {"label": "Total Robado (L)", "valor": f"{total_robado:,.2f}", "formula": "Suma balances (-) en paradas"},
        {"label": "Consumo Real (L)", "valor": f"{consumo_real:,.2f}", "formula": "(Ini + Cargas) - Final"},
        {"label": "Rend. Neto", "valor": f"{round(dist_total/consumo_neto, 2) if consumo_neto > 0 else 0} km/l", "formula": "Km / (Consumo Real - Robos)"}
    ]
    
    return resumen_visual, df_det, pd.DataFrame(eventos_movimiento)

# --- INTERFAZ ---
st.set_page_config(page_title="Reporte de Combustible", layout="wide")
col_titulo, col_reglas = st.columns([2, 1])

with col_titulo:
    st.title("📋 Reporte de Combustible")
    st.write("Auditoría Dual: Eventos en Parada + Rendimiento en Movimiento.")

with col_reglas:
    with st.expander("🔍 Reglas de Validación", expanded=True):
        st.markdown("""
        1. **Filtro Ruido Inicial:** Saltos < 2L al detenerse se ignoran.
        2. **Balance Neto:** Auditoría Entrada vs Salida en paradas.
        3. **Rendimiento Anómalo:** Si en movimiento el rendimiento es < 1.2 km/L, se marca como anomalía (posible robo en marcha).
        """)

file = st.file_uploader("Subir archivo CSV", type=['csv'])

if file:
    try:
        df_raw = pd.read_csv(file)
        resumen, df_det, df_mov = analizar_datos_pro(df_raw)
        
        st.subheader("📊 Balance General")
        cols = st.columns(len(resumen))
        for i, item in enumerate(resumen):
            with cols[i]:
                st.metric(label=item["label"], value=item["valor"])
                st.caption(f"fx: {item['formula']}")
        
        st.subheader("🚩 Detalle de Anomalías Detectadas (Detenido)")
        if not df_det.empty:
            st.table(df_det.sort_values('PI'))
        else:
            st.info("No hay anomalías en parada.")

        st.divider()

        st.subheader("🚚 Detalles de Anomalías Detectadas en Movimiento")
        if not df_mov.empty:
            st.warning("Se detectaron tramos con consumos excesivos de combustible.")
            st.table(df_mov.sort_values('Inicio'))
        else:
            st.success("No se detectaron rendimientos anómalos en movimiento.")
            
    except Exception as e:
        st.error(f"Error: {e}")
