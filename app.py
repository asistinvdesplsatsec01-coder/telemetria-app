import streamlit as st
import pandas as pd

def analizar_datos(df):
    df['Fecha Hora'] = pd.to_datetime(df['Fecha Hora'])
    df = df.sort_values('Fecha Hora')
    
    # Configuración de umbrales para Kenworth + Sensor Escort
    UMBRAL_ROBO_LITROS = -2.0  
    TASA_RALENTI_MAX = 0.08    
    
    df['diff_litros'] = df['Total combustible'].diff()
    df['diff_time'] = df['Fecha Hora'].diff().dt.total_seconds() / 60
    df['tasa_l_min'] = df['diff_litros'] / df['diff_time']
    
    eventos = []
    evento_actual = None

    for i in range(1, len(df)):
        fila = df.iloc[i]
        # Detectar anomalía: Detenido + bajada rápida
        is_anomaly = (fila['Velocidad'] == 0) and (fila['diff_litros'] < 0) and (abs(fila['tasa_l_min']) > TASA_RALENTI_MAX)
        
        if is_anomaly:
            if evento_actual is None:
                evento_actual = {'Tipo': 'POSIBLE ROBO', 'PI': fila['Fecha Hora'], 'Litros_I': df.iloc[i-1]['Total combustible']}
            evento_actual['PF'] = fila['Fecha Hora']
            evento_actual['Litros_F'] = fila['Total combustible']
        else:
            if evento_actual is not None:
                total = round(evento_actual['Litros_F'] - evento_actual['Litros_I'], 2)
                if total <= UMBRAL_ROBO_LITROS:
                    evento_actual['Total Litros'] = total
                    eventos.append(evento_actual)
                evento_actual = None

    # Detectar Cargas
    cargas = df[df['diff_litros'] > 10]
    for _, row in cargas.iterrows():
        eventos.append({'Tipo': 'CARGA', 'PI': row['Fecha Hora'], 'PF': row['Fecha Hora'], 'Total Litros': round(row['diff_litros'], 2)})
    
    return pd.DataFrame(eventos)

st.title("Auditor de Telemetría: Kenworth 2015")
st.write("Sube tu archivo CSV para detectar extracciones y cargas.")

archivo = st.file_uploader("Selecciona el CSV", type=['csv'])

if archivo:
    df_subido = pd.read_csv(archivo)
    resultados = analizar_datos(df_subido)
    if not resultados.empty:
        st.success("Análisis completado")
        st.dataframe(resultados)
    else:
        st.info("No se detectaron anomalías significativas.")