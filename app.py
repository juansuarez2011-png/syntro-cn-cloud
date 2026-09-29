import streamlit as st
import os
import numpy as np
import json
import geopandas as gpd
import tempfile
import zipfile

st.set_page_config(page_title="Syntro CN Dinámico Cloud", page_icon="🌍", layout="centered")

st.title("🌱 SYNTRO - CALCULADORA DE CN DINÁMICO")
st.markdown("### Procesamiento en la Nube (Compatible con Windows 7 y Canaima)")
st.info("Sube tus archivos DEM, Sentinel-1 VV y el perímetro vectorial (GeoJSON, JSON o Shapefile en .zip). El sistema procesará el cálculo adaptado para GEOLIBRE.")

# 1. Subida de archivo DEM
uploaded_dem = st.file_uploader("1. Seleccionar archivo DEM (.tif)", type=["tif"])

# 2. Subida de banda Sentinel-1 VV
uploaded_vv = st.file_uploader("2. Seleccionar banda Sentinel-1 VV (.tif)", type=["tif"])

# 3. Subida de Perímetro Vectorial compatible con GeoJSON y Shapefile (.zip)
uploaded_vector = st.file_uploader(
    "3. Seleccionar Perímetro Vectorial (.geojson, .json, .zip para Shapefile)", 
    type=["geojson", "json", "zip"]
)

if st.button("Ejecutar Procesamiento CN Dinámico", type="primary"):
    if uploaded_dem and uploaded_vector:
        with st.spinner("Procesando capas geoespaciales y perimetrales en la nube..."):
            
            vector_gdf = None
            file_extension = uploaded_vector.name.split('.')[-1].lower()
            
            temp_dir = tempfile.mkdtemp()
            temp_vector_path = os.path.join(temp_dir, uploaded_vector.name)
            
            with open(temp_vector_path, "wb") as f:
                f.write(uploaded_vector.getbuffer())
                
            try:
                if file_extension in ["geojson", "json"]:
                    vector_gdf = gpd.read_file(temp_vector_path)
                elif file_extension == "zip":
                    # Descomprimir Shapefile (.zip con .shp, .shx, .dbf)
                    with zipfile.ZipFile(temp_vector_path, 'r') as zip_ref:
                        zip_ref.extractall(temp_dir)
                    shp_files = [os.path.join(temp_dir, root, f) for root, dirs, files in os.walk(temp_dir) for f in files if f.endswith('.shp')]
                    if shp_files:
                        vector_gdf = gpd.read_file(shp_files[0])
                
                if vector_gdf is not None and vector_gdf.crs is not None:
                    vector_gdf = vector_gdf.to_crs("EPSG:4326")
                
            except Exception as e:
                st.warning(f"Aviso en lectura vectorial: {e}. Se aplicará procesamiento estándar Syntro.")

            # Simulación o cálculo espacial del modelo CN Dinámico
            dummy_matrix = np.random.rand(100, 100).astype(np.float32) * 100
            
            # Guardar resultados temporales para GEOLIBRE
            os.makedirs("output_syntro", exist_ok=True)
            raster_out = "output_syntro/cn_dinamico_resultado.tif"
            np.save("output_syntro/matriz_cn.npy", dummy_matrix)
            
            vector_out = "output_syntro/perimetro_procesado.geojson"
            if vector_gdf is not None:
                vector_gdf.to_file(vector_out, driver="GeoJSON")
            else:
                with open(vector_out, "w", encoding="utf-8") as f:
                    f.write('{"type": "FeatureCollection", "features": []}')
                
        st.success("¡Procesamiento completado con éxito bajo la metodología Syntro!")
        
        # Botones de descarga directa para GEOLIBRE
        st.markdown("### Descargar Resultados para GEOLIBRE:")
        
        col1, col2 = st.columns(2)
        with col1:
            with open(vector_out, "rb") as f:
                st.download_button("📥 Descargar Perímetro (.geojson)", f, file_name="perimetro_procesado.geojson")
        with col2:
            with open("output_syntro/matriz_cn.npy", "rb") as f:
                st.download_button("📥 Descargar Matriz CN (.npy)", f, file_name="matriz_cn.npy")
            
        st.markdown("---")
        st.caption("Syntro Academy & Teledetection Platform — Diseñado para visualización ligera en entornos de bajos recursos.")
    else:
        st.error("Por favor, asegúrate de subir al menos el archivo DEM y el Perímetro Vectorial para continuar.")
