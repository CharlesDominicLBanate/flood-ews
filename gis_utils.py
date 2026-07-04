"""
gis_utils.py
------------
Builds the Web-GIS hazard map (folium) showing every monitored location
color-coded by its current Flash Flood Risk Index.
"""

import folium
from folium.plugins import Fullscreen


def build_hazard_map(location_results: dict, center=(9.5, 122.5), zoom_start=6):
    """
    location_results: dict of {name: {"lat", "lon", "ffri", "risk_label",
                                       "risk_color", "elevation", ...}}
    """
    fmap = folium.Map(
        location=center,
        zoom_start=zoom_start,
        tiles="CartoDB positron",
        control_scale=True,
    )
    Fullscreen(position="topright").add_to(fmap)

    for name, info in location_results.items():
        lat, lon = info["lat"], info["lon"]
        ffri = info["ffri"]
        color = info["risk_color"]
        label = info["risk_label"]
        elevation = info.get("elevation", "N/A")

        # Risk radius scales with severity so hotspots visually pop
        radius = 12000 + (ffri / 100.0) * 28000

        popup_html = f"""
        <div style="font-family:Arial; font-size:13px; min-width:180px">
            <b style="font-size:15px">{name}</b><br>
            <span style="color:{color}; font-weight:bold; font-size:14px">
                {label} RISK
            </span><br>
            Flash Flood Risk Index: <b>{ffri:.1f} / 100</b><br>
            Elevation: {elevation:.0f} m<br>
        </div>
        """

        folium.Circle(
            location=(lat, lon),
            radius=radius,
            color=color,
            weight=2,
            fill=True,
            fill_color=color,
            fill_opacity=0.35,
            popup=folium.Popup(popup_html, max_width=250),
            tooltip=f"{name}: {label} ({ffri:.0f})",
        ).add_to(fmap)

        folium.Marker(
            location=(lat, lon),
            icon=folium.Icon(color="white", icon_color=color, icon="tint", prefix="fa"),
            tooltip=f"{name}: {label}",
        ).add_to(fmap)

    return fmap
