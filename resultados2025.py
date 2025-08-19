import streamlit as st
import pandas as pd
import geopandas as gpd
import folium
from streamlit_folium import folium_static
from shapely.geometry import shape
import requests
from branca.colormap import linear

# --- CARGA DE DATOS ---
@st.cache_data
def load_data():
    df_2025 = pd.read_csv("https://raw.githubusercontent.com/Facunfer/paginaresultados-2025/refs/heads/main/CONSOLIDACI%C3%93N%20DE%20RSULTADOS%202025%20-%20RESULTADOS%202025%20(1).csv")
    df_2023 = pd.read_csv("https://raw.githubusercontent.com/Facunfer/paginaresultados-2025/refs/heads/main/CONSOLIDACI%C3%93N%20RESULTADOS%20ELECCIONES%202023%20-%20Hoja%201%20(2).csv")

    geo_url = "https://raw.githubusercontent.com/tartagalensis/circuitos_electorales_AR/main/geojson/CABA.geojson"
    geojson = requests.get(geo_url).json()

    features = []
    for feat in geojson["features"]:
        props = feat["properties"]
        props["geometry"] = shape(feat["geometry"])
        features.append(props)

    gdf = gpd.GeoDataFrame(features, geometry="geometry", crs="EPSG:4326")
    gdf["circuito"] = gdf["circuito"].astype(str).str.zfill(5)

    return df_2025, df_2023, gdf

# --- FUNCIÓN PARA ETIQUETAS EN EL MAPA ---
def add_value_labels(m, gdf, col, formatter):
    """
    Coloca etiquetas con el valor de la columna `col` sobre cada polígono del GeoDataFrame `gdf`.
    Usa el punto representativo para que el texto quede dentro del polígono.
    """
    gdf_pts = gdf[gdf[col].notna()].copy()
    gdf_pts["__pt__"] = gdf_pts.geometry.representative_point()

    for _, row in gdf_pts.iterrows():
        val = row[col]
        try:
            text = formatter(val)
        except Exception:
            text = str(val)

        folium.Marker(
            location=[row["__pt__"].y, row["__pt__"].x],
            icon=folium.DivIcon(html=f"""
                <div style="
                    font-size:10px;
                    font-weight:700;
                    padding:2px 4px;
                    background: rgba(255,255,255,0.75);
                    border: 1px solid rgba(0,0,0,0.2);
                    border-radius: 4px;
                    box-shadow: 0 1px 2px rgba(0,0,0,0.2);
                    white-space: nowrap;
                ">
                    {text}
                </div>
            """)).add_to(m)

# ======================
# APP
# ======================
df_2025, df_2023, geo = load_data()

# --- NORMALIZACIÓN ---
df_2025.columns = df_2025.columns.str.lower().str.strip()
df_2023.columns = df_2023.columns.str.lower().str.strip()

df_2025.rename(columns={"descripcion_candidatura": "partido", "sum cant_votos": "votos"}, inplace=True)
df_2023.rename(columns={"agrupacion_nombre": "partido", "sum votos_cantidad": "votos", "circuito_id": "circuito"}, inplace=True)

df_2025["partido"] = df_2025["partido"].str.upper()
df_2023["partido"] = df_2023["partido"].str.upper()
df_2025["circuito"] = df_2025["circuito"].astype(str).str.zfill(5)
df_2023["circuito"] = df_2023["circuito"].astype(str).str.zfill(5)

# --- ASIGNAR COLUMNA DE COMUNA ---
if "comuna" in df_2025.columns:
    df_2025["COMUNA"] = df_2025["comuna"].astype(str).str.upper()
else:
    st.error("No se encontró la columna 'comuna' en df_2025.")
    st.stop()

if "seccion_nombre" in df_2023.columns:
    df_2023["COMUNA"] = df_2023["seccion_nombre"].astype(str).str.upper()
else:
    st.error("No se encontró la columna 'seccion_nombre' en df_2023.")
    st.stop()

# --- AGRUPACIÓN PRINCIPAL ---
agrupacion = {
    "LA LIBERTAD AVANZA": "LLA",
    "ES AHORA BUENOS AIRES": "AHORA",
    "UNION POR LA PATRIA": "AHORA"
}

df_2025_agrup = df_2025[df_2025["partido"].isin(agrupacion)].copy()
df_2025_agrup["grupo"] = df_2025_agrup["partido"].map(agrupacion)

pivot_2025 = df_2025_agrup.pivot_table(
    index="circuito",
    columns="grupo",
    values="votos",
    aggfunc="sum",
    fill_value=0
).reset_index()

pivot_2023 = (
    df_2023[df_2023["partido"] == "LA LIBERTAD AVANZA"]
    .groupby("circuito")["votos"]
    .sum()
    .reset_index(name="votos_2023")
)

total_2025 = df_2025.groupby("circuito")["votos"].sum().reset_index(name="total_2025")
total_2023 = df_2023.groupby("circuito")["votos"].sum().reset_index(name="total_2023")

df_final = (
    pivot_2025
    .merge(pivot_2023, on="circuito", how="outer")
    .merge(total_2025, on="circuito", how="left")
    .merge(total_2023, on="circuito", how="left")
)
df_final.fillna(0, inplace=True)

df_final["GANADOR"] = df_final.apply(lambda x: "LLA" if x.get("LLA", 0) > x.get("AHORA", 0) else "AHORA", axis=1)
df_final["PORC_2025"] = df_final["LLA"] / df_final["total_2025"] * 100
df_final["PORC_2023"] = df_final["votos_2023"] / df_final["total_2023"] * 100
df_final["DIF_ABS"] = df_final["LLA"] - df_final["votos_2023"]
df_final["DIF_PORC"] = df_final["PORC_2025"] - df_final["PORC_2023"]

# --- TOOLTIP EXTRA: VOTOS POR PARTIDO ---
df_tooltip = df_2025[df_2025["partido"].isin([
    "LA LIBERTAD AVANZA", "ES AHORA BUENOS AIRES", "BUENOS AIRES PRIMERO"
])]
pivot_tooltip = df_tooltip.pivot_table(
    index="circuito",
    columns="partido",
    values="votos",
    aggfunc="sum",
    fill_value=0
).reset_index()
pivot_tooltip.columns.name = None
pivot_tooltip.rename(columns={
    "LA LIBERTAD AVANZA": "LLA_TIP",
    "ES AHORA BUENOS AIRES": "AHORA_TIP",
    "BUENOS AIRES PRIMERO": "BA_PRIMERO_TIP"
}, inplace=True)

pivot_tooltip["circuito"] = pivot_tooltip["circuito"].astype(str).str.zfill(5)
df_final = df_final.merge(pivot_tooltip, on="circuito", how="left")

# --- AÑADIR COMUNA A df_final ---
comuna_por_circuito = df_2025[["circuito", "COMUNA"]].drop_duplicates()
df_final = df_final.merge(comuna_por_circuito, on="circuito", how="left")

# --- UNIÓN CON GEO ---
geo_final = geo.merge(df_final, on="circuito", how="left")

# --- STREAMLIT INTERFAZ ---
st.title("🗳️ Análisis Electoral por Circuito - CABA")

# --- FILTRO POR COMUNA ---
comunas_disponibles = sorted(geo_final["COMUNA"].dropna().unique())
comuna_seleccionada = st.selectbox("Filtrar por comuna:", ["Todas"] + comunas_disponibles)

if comuna_seleccionada != "Todas":
    geo_filtrado = geo_final[geo_final["COMUNA"] == comuna_seleccionada].copy()
else:
    geo_filtrado = geo_final.copy()

# --- VISTA ---
vista = st.selectbox("Seleccioná la vista:", [
    "1. Ganador por Circuito",
    "2. Cantidad de Votos LLA 2025",
    "3. Porcentaje LLA 2025",
    "4. Crecimiento en Votos",
    "5. Crecimiento Porcentual"
])

# --- Check para mostrar/ocultar etiquetas ---
mostrar_etiquetas = st.checkbox("Mostrar etiquetas sobre el mapa (valores/porcentaje)", value=True)

# --- MAPA ---
m = folium.Map(location=[-34.61, -58.42], zoom_start=11)

if vista.startswith("1"):
    folium.GeoJson(
        geo_filtrado,
        style_function=lambda feature: {
            "fillColor": "purple" if feature["properties"].get("GANADOR") == "LLA" else "green",
            "color": "black",
            "weight": 0.5,
            "fillOpacity": 0.7,
        },
        tooltip=folium.GeoJsonTooltip(
            fields=["circuito", "LLA_TIP", "AHORA_TIP", "BA_PRIMERO_TIP"],
            aliases=["Circuito", "LLA votos", "Ahora BsAs votos", "BA Primero votos"],
            localize=True
        )
    ).add_to(m)
else:
    capa_info = {
        "2": ("LLA", "Votos LLA 2025",
              lambda x: f"{int(pd.to_numeric(x, errors='coerce') or 0):,}".replace(",", ".") + " votos"),
        "3": ("PORC_2025", "% LLA 2025",
              lambda x: f"{float(pd.to_numeric(x, errors='coerce') or 0):.1f}%"),
        "4": ("DIF_ABS", "Crecimiento absoluto",
              lambda x: f"{int(pd.to_numeric(x, errors='coerce') or 0):+} votos"),
        "5": ("DIF_PORC", "Crecimiento porcentual",
              lambda x: f"{float(pd.to_numeric(x, errors='coerce') or 0):+.1f}%")
    }

    col, legend, formatear = capa_info[vista[0]]

    # Asegurar numérico para la escala de colores
    geo_filtrado[col] = pd.to_numeric(geo_filtrado[col], errors="coerce")

    vmin = float(geo_filtrado[col].min() if pd.notna(geo_filtrado[col].min()) else 0)
    vmax = float(geo_filtrado[col].max() if pd.notna(geo_filtrado[col].max()) else 0)

    color_map = linear.RdYlGn_11.scale(vmin, vmax).to_step(n=10)
    color_map.caption = legend

    folium.GeoJson(
        geo_filtrado,
        style_function=lambda feat: {
            "fillColor": color_map(feat["properties"][col]) if feat["properties"].get(col) is not None else "gray",
            "color": "black",
            "weight": 0.5,
            "fillOpacity": 0.7,
        },
        tooltip=folium.GeoJsonTooltip(
            fields=["circuito", col],
            aliases=["Circuito", legend],
            localize=True,
            labels=True
        )
    ).add_to(m)

    color_map.add_to(m)

    # --- ETIQUETAS SOBRE EL MAPA SOLO PARA VISTAS 2 y 3 ---
    if mostrar_etiquetas and vista[0] in ("2", "3"):
        if vista[0] == "2":
            fmt_etiqueta = lambda x: f"{int(pd.to_numeric(x, errors='coerce') or 0):,}".replace(",", ".")
        else:
            fmt_etiqueta = lambda x: f"{float(pd.to_numeric(x, errors='coerce') or 0):.1f}%"

        add_value_labels(m, geo_filtrado, col, fmt_etiqueta)

folium_static(m)

