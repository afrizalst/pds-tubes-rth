import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from folium.plugins import HeatMap, MarkerCluster
import plotly.express as px
import os

# --- 1. IMPORT PETA OFFLINE ---
try:
    from data_peta import geojson_bandung
except ImportError:
    st.error(" File 'data_peta.py' tidak ada! Pastikan file itu ada di folder ini.")
    st.stop()

# --- 2. KONFIGURASI HALAMAN ---
st.set_page_config(
    page_title="Dashboard RTH Bandung",
    page_icon="🌳",
    layout="wide"
)

# --- 3. LOAD DATA ---
@st.cache_data
def load_data():
    # Baca file CSV
    if os.path.exists("data_LAT_LON.csv"):
        df = pd.read_csv("data_LAT_LON.csv")
    else:
        return None

    # A. Cleaning Nama Kecamatan
    if 'kecamatan' in df.columns:
        df['kecamatan'] = df['kecamatan'].fillna("Tanpa Nama").astype(str).str.title()
    
    # B. Simplifikasi Kategori (TAMAN vs LAIN-LAIN)
    def simplifikasi(kat):
        return "TAMAN" if "TAMAN" in str(kat).upper() else "LAIN-LAIN"
    
    if 'kategori' in df.columns:
        df['jenis_filter'] = df['kategori'].apply(simplifikasi)
    else:
        df['jenis_filter'] = "LAIN-LAIN"
        df['kategori'] = "Umum"
        
    return df

df = load_data()

if df is None:
    st.error("File 'data_LAT_LON.csv' tidak ditemukan! Coba periksa lagi.")
    st.stop()

# --- 4. SIDEBAR: KONTROL UTAMA ---
st.sidebar.title("Kontrol Panel")

# --- FILTER KECAMATAN ---
all_kecamatan = sorted(df['kecamatan'].unique())

st.sidebar.subheader("Pilih Kecamatan")
selected_kecamatan = st.sidebar.multiselect(
    "Cari Kecamatan:",
    all_kecamatan,
    default=[] # DEFAULT KOSONG 
)

# --- LOGIKA STOP ---
if not selected_kecamatan:
    st.title(" Selamat Datang di Dashboard RTH Kota Bandung")
    st.info("👈 **Silakan pilih satu atau lebih Kecamatan di Sidebar sebelah kiri untuk memunculkan data.**")
    st.stop() 

# --- SCRIPT BERLANJUT JIKA KECAMATAN SUDAH DIPILIH  ---

# Filter Dataset
df_filtered = df[df['kecamatan'].isin(selected_kecamatan)]

# Filter Tambahan (Target & Jenis)
st.sidebar.divider()
target_rth = st.sidebar.slider("Target RTH per Kecamatan:", 10, 100, 30, 5)
mode_heatmap = st.sidebar.checkbox(" Mode Heatmap", value=False)
tampil_batas = st.sidebar.checkbox(" Batas Wilayah", value=True)

# --- 5. ANALISIS DATA (GAP ANALYSIS) ---
analisis_df = df.groupby('kecamatan').size().reset_index(name='jumlah_eksisting')
analisis_df['target'] = target_rth
analisis_df['selisih'] = analisis_df['jumlah_eksisting'] - target_rth
analisis_df['persentase'] = (analisis_df['jumlah_eksisting'] / target_rth) * 100

def get_status(selisih):
    if selisih >= 0: return "AMAN"
    elif selisih >= -10: return "WASPADA"
    else: return "KRITIS"
analisis_df['status'] = analisis_df['selisih'].apply(get_status)

# Filter analisis sesuai kecamatan yg dipilih
analisis_filtered = analisis_df[analisis_df['kecamatan'].isin(selected_kecamatan)]

# --- 6. DASHBOARD UTAMA ---
st.title(f" Analisis: {', '.join(selected_kecamatan[:3])}" + (", dst..." if len(selected_kecamatan)>3 else ""))

# --- MENGHITUNG SELISIH ---
col1, col2, col3 = st.columns(3)
col1.metric("Total Titik Terpilih", len(df_filtered))
col2.metric("Kekurangan RTH", f"{analisis_filtered[analisis_filtered['selisih'] < 0]['selisih'].sum()} Titik", delta_color="inverse")
col3.metric("Status Dominan", analisis_filtered['status'].mode()[0] if not analisis_filtered.empty else "-")

st.divider()

# --- 7. TABS VISUALISASI ---
tab1, tab2, tab3 = st.tabs([" Peta Lokasi", " Grafik & Analisis", " Data Tabel"])

# === TAB 1: PETA GIS ===
with tab1:
    # Cari tengah peta berdasarkan data yang dipilih biar fokus
    avg_lat = df_filtered['latitude'].mean()
    avg_lon = df_filtered['longitude'].mean()
    m = folium.Map(location=[avg_lat, avg_lon], zoom_start=14)

    # Layer Batas Wilayah
    if tampil_batas:
        # Filter GeoJSON manual biar enteng (hanya tampilkan batas kecamatan yg dipilih)
        filtered_geojson = {
            "type": "FeatureCollection",
            "features": [
                f for f in geojson_bandung['features'] 
                if f['properties']['nama_kecamatan'].title() in selected_kecamatan
            ]
        }
        
        folium.GeoJson(
            filtered_geojson,
            name="Batas Wilayah",
            style_function=lambda x: {'fillColor': x['properties'].get('fillColor', 'gray'), 'color': 'black', 'weight': 2, 'fillOpacity': 0.1},
            tooltip=folium.GeoJsonTooltip(fields=['nama_kecamatan'], aliases=['Kecamatan: '])
        ).add_to(m)

    # Layer Heatmap / Marker
    df_map = df_filtered.dropna(subset=['latitude', 'longitude'])
    
    if mode_heatmap:
        heat_data = [[row['latitude'], row['longitude']] for _, row in df_map.iterrows()]
        HeatMap(heat_data, radius=15, blur=10).add_to(m)
    else:
        marker_cluster = MarkerCluster().add_to(m)
        for _, row in df_map.iterrows():
            warna = "green" if row['jenis_filter'] == 'TAMAN' else "blue"
            icon = "tree" if row['jenis_filter'] == 'TAMAN' else "info-sign"
            
            popup_html = f"<b>{row['lokasi']}</b><br>{row['kategori']}<br>Status: {row.get('status_akurasi', '-')}"
            
            folium.Marker(
                [row['latitude'], row['longitude']],
                popup=folium.Popup(popup_html, max_width=200),
                tooltip=row['lokasi'],
                icon=folium.Icon(color=warna, icon=icon, prefix="glyphicon")
            ).add_to(marker_cluster)

    st_folium(m, width="100%", height=500)

# === TAB 2: GRAFIK ===
with tab2:
    col_g1, col_g2 = st.columns(2)
    
    with col_g1:
        # Grafik Gap Analysis
        st.subheader("Target vs Realisasi")
        fig_gap = px.bar(
            analisis_filtered,
            x='selisih', y='kecamatan', orientation='h',
            title=f"Kekurangan/Kelebihan (Target: {target_rth})",
            color='selisih',
            color_continuous_scale='RdYlGn', # Merah (Kurang) -> Hijau (Lebih)
            text='selisih'
        )
        st.plotly_chart(fig_gap, use_container_width=True)
        
    with col_g2:
        # Grafik Jenis
        st.subheader("Komposisi RTH")
        count_jenis = df_filtered.groupby('jenis_filter').size().reset_index(name='jumlah')
        fig_pie = px.pie(
            count_jenis, names='jenis_filter', values='jumlah',
            color='jenis_filter',
            color_discrete_map={'TAMAN': '#2ecc71', 'LAIN-LAIN': '#3498db'},
            hole=0.4
        )
        st.plotly_chart(fig_pie, use_container_width=True)

# === TAB 3: DATA TABEL ===
with tab3:
    st.subheader("Detail Data Terpilih")
    st.dataframe(df_filtered[['kecamatan', 'kelurahan', 'lokasi', 'kategori', 'jenis_filter']], use_container_width=True)