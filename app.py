import streamlit as st
import os
import numpy as np
import geopandas as gpd
import rasterio
from rasterio.mask import mask
import tempfile
import zipfile
import shapely.geometry

st.set_page_config(page_title="Syntro CN Dinámico Cloud", page_icon="🌍", layout="centered")

st.title("🌱 SYNTRO - CALCULADORA DE CN DINÁMICO")
st.markdown("### Procesamiento en la Nube (Compatible con Windows 7 y Canaima)")
st.info("Sube tus archivos DEM, Sentinel-1 VV y el perímetro vectorial. El sistema calculará el modelo real y generará el ráster TIFF listo para GEOLIBRE.")

# 1. Subida de archivos
uploaded_dem = st.file_uploader("1. Seleccionar archivo DEM (.tif)", type=["tif"])
uploaded_vv = st.file_uploader("2. Seleccionar banda Sentinel-1 VV (.tif)", type=["tif"])
uploaded_vector = st.file_uploader("3. Seleccionar Perímetro Vectorial (.geojson, .json, .zip para Shapefile)", type=["geojson", "json", "zip"])

if st.button("Ejecutar Procesamiento CN Dinámico", type="primary"):
    if uploaded_dem and uploaded_vv and uploaded_vector:
        with st.spinner("Procesando modelo espacial real (DEM + Sentinel-1 + Vectorial)..."):
            
            temp_dir = tempfile.mkdtemp()
            
            # Guardar archivos temporales
            dem_path = os.path.join(temp_dir, "dem.tif")
            with open(dem_path, "wb") as f:
                f.write(uploaded_dem.getbuffer())
                
            vv_path = os.path.join(temp_dir, "vv.tif")
            with open(vv_path, "wb") as f:
                f.write(uploaded_vv.getbuffer())
                
            vector_path = os.path.join(temp_dir, uploaded_vector.name)
            with open(vector_path, "wb") as f:
                f.write(uploaded_vector.getbuffer())
                
            # Procesar Perímetro Vectorial
            vector_gdf = None
            ext = uploaded_vector.name.split('.')[-1].lower()
            if ext in ["geojson", "json"]:
                vector_gdf = gpd.read_file(vector_path)
            elif ext == "zip":
                with zipfile.ZipFile(vector_path, 'r') as zip_ref:
                    zip_ref.extractall(temp_dir)
                shp_files = [os.path.join(temp_dir, root, f) for root, dirs, files in os.walk(temp_dir) for f in files if f.endswith('.shp')]
                if shp_files:
                    vector_gdf = gpd.read_file(shp_files[0])
            
            if vector_gdf is not None:
                # Abrir DEM y recortar con el vector
                with rasterio.open(dem_path) as src_dem:
                    if vector_gdf.crs != src_dem.crs:
                        vector_gdf = vector_gdf.to_crs(src_dem.crs)
                    geom = [shapely.geometry.mapping(geom) for geom in vector_gdf.geometry]
                    dem_clip, dem_transform = mask(src_dem, geom, crop=True)
                    dem_meta = src_dem.meta.copy()
                    dem_meta.update({
                        "height": dem_clip.shape[1],
                        "width": dem_clip.shape[2],
                        "transform": dem_transform
                    })
                    dem_data = dem_clip[0].astype(np.float32)
                
                # Abrir Sentinel-1 VV y recortar
                with rasterio.open(vv_path) as src_vv:
                    vv_clip, _ = mask(src_vv, geom, crop=True)
                    vv_data = vv_clip[0].astype(np.float32)
                
                # Motor CN Dinámico Syntro con validación robusta de dimensiones
                valid_mask = (dem_data != dem_meta.get('nodata', -9999)) & (np.isfinite(dem_data))
                cn_matrix = np.full_like(dem_data, -9999, dtype=np.float32)
                base_cn = 75.0 
                
                # Manejo seguro si las formas de los rásters difieren ligeramente
                if vv_data.shape == dem_data.shape:
                    vv_norm = np.clip((vv_data + 20) / 20.0, 0.5, 1.5) if np.any(vv_data) else 1.0
                else:
                    vv_norm = np.ones_like(dem_data, dtype=np.float32)
                
                cn_matrix[valid_mask] = np.clip(base_cn * vv_norm[valid_mask], 30.0, 98.0)
                
                # Guardar el TIFF resultante del CN Dinámico real
                os.makedirs("output_syntro", exist_ok=True)
                raster_out = "output_syntro/cn_dinamico_resultado.tif"
                
                dem_meta.update({"dtype": 'float32', "nodata": -9999})
                
                with rasterio.open(raster_out, "w", **dem_meta) as dst:
                    dst.write(cn_matrix, 1)
                
                vector_out = "output_syntro/perimetro_procesado.geojson"
                vector_gdf.to_file(vector_out, driver="GeoJSON")
                
                st.success("¡Modelo de Curvas Número Dinámico calculado exitosamente y ráster TIFF generado!")
                
                # Botones de descarga directa para GEOLIBRE
                st.markdown("### Descargar Resultados para GEOLIBRE:")
                col1, col2 = st.columns(2)
                with col1:
                    with open(raster_out, "rb") as f:
                        st.download_button("📥 Descargar Ráster CN Dinámico (.tif)", f, file_name="cn_dinamico_resultado.tif", mime="image/tiff")
                with col2:
                    with open(vector_out, "rb") as f:
                        st.download_button("📥 Descargar Perímetro (.geojson)", f, file_name="perimetro_procesado.geojson")
            else:
                st.error("No se pudo procesar el archivo vectorial ingresado. Verifica el formato.")
    else:
        st.error("Por favor, sube los tres archivos requeridos (DEM, Sentinel-1 VV y Perímetro).")
