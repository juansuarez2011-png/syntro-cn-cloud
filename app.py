import streamlit as st
import os
import numpy as np
import geopandas as gpd
import rasterio
from rasterio.mask import mask
from rasterio.features import rasterize, shapes
from scipy.ndimage import gaussian_filter
import tempfile
import zipfile
import shapely.geometry

st.set_page_config(page_title="Syntro CN Dinámico Cloud", page_icon="🌍", layout="centered")

st.title("🌱 SYNTRO - CALCULADORA DE CN DINÁMICO")
st.markdown("### Procesamiento en la Nube (Compatible con Windows 7 y Canaima)")
st.info("Sube tu ZIP de Sentinel-1 (VV), el DEM (.tif) y el Perímetro de la Finca. El sistema calculará el modelo hidrológico real, el área por grupos y generará los resultados listos para GEOLIBRE.")

# 1. Subida de archivos
uploaded_s1 = st.file_uploader("1. Seleccionar archivo ZIP Sentinel-1 (VV)", type=["zip"])
uploaded_dem = st.file_uploader("2. Seleccionar Modelo de Elevación Digital (DEM - TIFF)", type=["tif", "tiff"])
uploaded_vector = st.file_uploader("3. Perímetro de la Finca (Shapefile en .zip, GeoJSON o JSON)", type=["shp", "geojson", "json", "zip"])

if st.button("EJECUTAR MODELO Y EXPORTAR GEOJSON", type="primary"):
    if uploaded_s1 and uploaded_dem and uploaded_vector:
        with st.spinner("Ejecutando modelo hidrológico dinámico USDA AMC + cálculo de áreas..."):
            
            temp_dir = tempfile.mkdtemp()
            
            # Guardar archivos temporales
            s1_zip_path = os.path.join(temp_dir, uploaded_s1.name)
            with open(s1_zip_path, "wb") as f:
                f.write(uploaded_s1.getbuffer())
                
            dem_path = os.path.join(temp_dir, uploaded_dem.name)
            with open(dem_path, "wb") as f:
                f.write(uploaded_dem.getbuffer())
                
            vector_path = os.path.join(temp_dir, uploaded_vector.name)
            with open(vector_path, "wb") as f:
                f.write(uploaded_vector.getbuffer())
                
            # Extraer banda VV del ZIP de Sentinel-1
            s1_raster = None
            extract_s1_dir = os.path.join(temp_dir, "s1_ext")
            os.makedirs(extract_s1_dir, exist_ok=True)
            with zipfile.ZipFile(s1_zip_path, 'r') as z:
                for filename in z.namelist():
                    if filename.lower().endswith(('.tif', '.tiff')) and 'vv' in filename.lower():
                        z.extract(filename, extract_s1_dir)
                        s1_raster = os.path.join(extract_s1_dir, filename)
                        break
            
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
            
            if s1_raster and vector_gdf is not None:
                # Procesar DEM y enmascarar con el perímetro
                with rasterio.open(dem_path) as src:
                    if vector_gdf.crs and str(vector_gdf.crs) != str(src.crs):
                        vector_gdf = vector_gdf.to_crs(src.crs)
                    meta = src.meta.copy()
                    
                    dem_full = src.read(1).astype(np.float32)
                    dem_nodata = src.nodata if src.nodata is not None else -9999.0
                    dem_full[dem_full == dem_nodata] = np.nan

                    shapes_list = [(g, 1) for g in vector_gdf.geometry]
                    mask_arr = rasterize(shapes_list, out_shape=(src.height, src.width), transform=src.transform, fill=0, default_value=1, dtype=np.uint8)
                    dem_data = np.where(mask_arr == 1, dem_full, np.nan)

                # Procesar banda Sentinel-1 VV
                with rasterio.open(s1_raster) as s1_src:
                    s1_res = s1_src.read(out_shape=(src.height, src.width), resampling=rasterio.enums.Resampling.bilinear)[0].astype(np.float32)
                    s1_nodata = s1_src.nodata
                    if s1_nodata is not None:
                        s1_res[s1_res == s1_nodata] = np.nan
                    s1_res[s1_res < -40.0] = np.nan
                    s1_res[s1_res > 10.0] = np.nan

                # Cálculo de pendientes y modelo dinámico Syntro
                dem_clean = np.nan_to_num(dem_data, nan=np.nanmedian(dem_data))
                zy = gaussian_filter(dem_clean, sigma=2.0)
                dx, dy = np.gradient(zy, 4.77, 4.77)
                slope = np.clip(np.sqrt(dx**2 + dy**2) * 100.0, 0.0, 150.0)
                slope = np.where(mask_arr == 1, slope, np.nan)

                cn_base = 70.0
                s1_lin = 10.0 ** (s1_res / 10.0)
                p_min = np.nanpercentile(s1_lin, 2)
                p_max = np.nanpercentile(s1_lin, 98)
                mi = np.clip((s1_lin - p_min) / (p_max - p_min + 1e-6), 0.0, 1.0)
                
                cn_i = cn_base / (2.280 - 0.01281 * cn_base)
                cn_iii = cn_base / (0.427 + 0.00573 * cn_base)
                
                cn_matrix = np.where(mi <= 0.5, cn_i + (cn_base - cn_i) * (mi * 2.0), cn_base + (cn_iii - cn_base) * ((mi - 0.5) * 2.0))
                cn_matrix = np.clip(cn_matrix + (slope * 0.05), 30.0, 95.0)
                
                final_cn = np.full(cn_matrix.shape, -9999.0, dtype=np.float32)
                valid_idx = (mask_arr == 1) & (~np.isnan(cn_matrix)) & (cn_matrix >= 30.0)
                final_cn[valid_idx] = cn_matrix[valid_idx]

                # Guardar Ráster TIFF resultante
                os.makedirs("output_syntro", exist_ok=True)
                raster_out = "output_syntro/CN_Dinamico_Syntro.tif"
                meta.update({
                    "driver": "GTiff",
                    "height": final_cn.shape[0],
                    "width": final_cn.shape[1],
                    "count": 1,
                    "dtype": "float32",
                    "nodata": -9999.0
                })

                with rasterio.open(raster_out, "w", **meta) as dst:
                    dst.write(final_cn, 1)

                # Generación de polígonos clasificados y asignación de Grupos Hidrológicos
                class_matrix = np.zeros(final_cn.shape, dtype=np.int32)
                v_mask = (final_cn != -9999.0) & (~np.isnan(final_cn))
                
                class_matrix[(final_cn >= 30.0) & (final_cn <= 55.0) & v_mask] = 1  # Grupo A
                class_matrix[(final_cn > 55.0) & (final_cn <= 70.0) & v_mask] = 2  # Grupo B
                class_matrix[(final_cn > 70.0) & (final_cn <= 80.0) & v_mask] = 3  # Grupo C
                class_matrix[(final_cn > 80.0) & (final_cn <= 95.0) & v_mask] = 4  # Grupo D

                geom_results = []
                transform = meta['transform']
                for geom, val in shapes(class_matrix.astype(np.uint8), transform=transform):
                    if val > 0:
                        poly_mask = rasterio.features.geometry_mask([geom], out_shape=final_cn.shape, transform=transform, invert=True)
                        vals_in_poly = final_cn[poly_mask & v_mask]
                        mean_cn_poly = float(np.mean(vals_in_poly)) if vals_in_poly.size > 0 else 0.0
                        geom_results.append({
                            'properties': {'id_grupo': int(val), 'cn_valor': round(mean_cn_poly, 2)},
                            'geometry': geom
                        })

                geojson_path = "output_syntro/Grupos_Hidrologicos_Syntro.geojson"
                if geom_results:
                    gdf_groups = gpd.GeoDataFrame.from_features(geom_results, crs=meta['crs'])
                    
                    # Proyección automática a UTM métrica para cálculo exacto de área
                    if gdf_groups.crs and gdf_groups.crs.is_geographic:
                        centroid = gdf_groups.unary_union.centroid
                        utm_zone = int((centroid.x + 180) / 6) + 1
                        hemisphere = 'north' if centroid.y >= 0 else 'south'
                        epsg_utm = 32600 + utm_zone if hemisphere == 'north' else 32700 + utm_zone
                        gdf_metric = gdf_groups.to_crs(epsg=epsg_utm)
                    else:
                        gdf_metric = gdf_groups

                    gdf_metric['area_m2'] = gdf_metric.geometry.area
                    gdf_metric['area_ha'] = gdf_metric['area_m2'] / 10000.0

                    grupo_info = {
                        1: {"Grupo": "A", "Infiltracion": "> 11.4 mm/h (Alta)", "Suelo": "Arenosos, profundos, muy permeables."},
                        2: {"Grupo": "B", "Infiltracion": "5.7 a 11.4 mm/h (Moderada)", "Suelo": "Francos, permeabilidad moderada."},
                        3: {"Grupo": "C", "Infiltracion": "1.4 a 5.7 mm/h (Moderada a Baja)", "Suelo": "Franco-arcillosos, capas que impiden drenaje."},
                        4: {"Grupo": "D", "Infiltracion": "< 1.4 mm/h (Muy Baja)", "Suelo": "Arcillosos pesados, texturas finas compactadas."}
                    }

                    gdf_groups['area_m2'] = gdf_metric['area_m2']
                    gdf_groups['area_ha'] = gdf_metric['area_ha']
                    gdf_groups['cn_valor'] = gdf_metric['cn_valor']
                    gdf_groups['Grupo_Hidro'] = gdf_groups['id_grupo'].map(lambda x: grupo_info.get(x, {}).get("Grupo", "N/A"))
                    gdf_groups['Infiltracion'] = gdf_groups['id_grupo'].map(lambda x: grupo_info.get(x, {}).get("Infiltracion", "N/A"))
                    gdf_groups['Suelo'] = gdf_groups['id_grupo'].map(lambda x: grupo_info.get(x, {}).get("Suelo", "N/A"))

                    # Guardar GeoJSON enriquecido con atributos y áreas
                    gdf_groups.to_file(geojson_path, driver="GeoJSON")

                st.success("¡Modelo completado! Áreas calculadas e incrustadas en el GeoJSON.")
                
                # Mostrar resumen de áreas por grupo hidrológico en pantalla
                st.markdown("### 📊 Resumen de Áreas por Grupo Hidrológico:")
                resumen_df = gdf_groups.groupby('Grupo_Hidro')['area_ha'].sum().reset_index()
                resumen_df['Porcentaje (%)'] = (resumen_df['area_ha'] / resumen_df['area_ha'].sum()) * 100
                st.dataframe(resumen_df.style.format({'area_ha': '{:.2f} ha', 'Porcentaje (%)': '{:.2f}%'}))

                # Botones de descarga para GEOLIBRE
                st.markdown("### Descargar Resultados para GEOLIBRE:")
                col1, col2 = st.columns(2)
                with col1:
                    with open(raster_out, "rb") as f:
                        st.download_button("📥 Descargar Ráster CN Dinámico (.tif)", f, file_name="CN_Dinamico_Syntro.tif", mime="image/tiff")
                with col2:
                    with open(geojson_path, "rb") as f:
                        st.download_button("📥 Descargar GeoJSON con Áreas (.geojson)", f, file_name="Grupos_Hidrologicos_Syntro.geojson", mime="application/json")
            else:
                st.error("Error al procesar los archivos de entrada.")
    else:
        st.error("Por favor, completa la carga de todos los archivos requeridos.")
