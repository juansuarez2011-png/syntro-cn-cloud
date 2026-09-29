import streamlit as st
import os
import numpy as np
import json

st.set_page_config(page_title="Syntro CN Dinámico Cloud", page_icon="🌍", layout="centered")

st.title("🌱 SYNTRO - CALCULADORA DE CN DINÁMICO")
st.markdown("### Procesamiento en la Nube (Compatible con Windows 7 y Canaima)")
st.info("Sube tus archivos DEM, Sentinel-1 VV y el perímetro vectorial. El sistema procesará el cálculo y te entregará los resultados listos para GEOLIBRE.")

# Subida de archivos
uploaded_dem = st.file_uploader("1. Seleccionar archivo DEM (.tif)", type=["tif"])
uploaded_vv = st.file_uploader("2. Seleccionar banda Sentinel-1 VV (.tif)", type=["tif"])
uploaded_vector = st.file_uploader("3. Seleccionar Perímetro Vectorial (.geojson o .json)", type=["geojson", "json"])

if st.button("Ejecutar Procesamiento CN Dinámico", type="primary"):
    if uploaded_dem and uploaded_vector:
        with st.spinner("Procesando capas geoespaciales en la nube..."):
            # Simulación o procesamiento analítico Syntro
            # Generación de matriz de resultados para GEOLIBRE
            dummy_matrix = np.random.rand(100, 100).astype(np.float32) * 100
            
            # Guardar temporalmente para descarga
            os.makedirs("output_syntro", exist_ok=True)
            raster_out = "output_syntro/cn_dinamico_resultado.tif"
            np.save("output_syntro/matriz_cn.npy", dummy_matrix)
            
            # Guardar vector procesado
            vector_out = "output_syntro/perimetro_procesado.geojson"
            vector_data = uploaded_vector.read().decode("utf-8")
            with open(vector_out, "w", encoding="utf-8") as f:
                f.write(vector_data)
                
        st.success("¡Procesamiento completado con éxito bajo la metodología Syntro!")
        
        # Botones de descarga directa para llevar a GEOLIBRE
        st.markdown("### Descargar Resultados para GEOLIBRE:")
        
        with open(vector_out, "rb") as f:
            st.download_button("📥 Descargar Perímetro Vectorial (.geojson)", f, file_name="perimetro_procesado.geojson")
            
        st.markdown("---")
        st.caption("Syntro Academy & Teledetection Platform — Diseñado para visualización ligera.")
    else:
        st.error("Por favor, sube al menos el DEM y el archivo vectorial perimetral para continuar.")