import io
import base64

import numpy as np
import folium
from folium.plugins import Fullscreen
from scipy.interpolate import griddata
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors


# Same color language as config.RISK_LEVELS (green -> yellow -> orange -> red)
_CONTOUR_COLORS = ["#1e8f4e", "#2ecc71", "#f1c40f", "#e67e22", "#e74c3c", "#8e1c1c"]
_CONTOUR_CMAP = mcolors.LinearSegmentedColormap.from_list("risk_contour", _CONTOUR_COLORS)


def _build_contour_overlay_png(location_results: dict, value_key: str = "ffri",
                                grid_res: int = 220, padding_deg: float = 1.25):
    """
    Interpolates a scalar field (default: FFRI) across the monitored sites and
    rasterizes it as a smooth filled-contour PNG (base64), the same visual
    language as an NWS-style precipitation contour map.

    IMPORTANT CAVEAT (say this in your defense if asked): NWS contour maps like
    the one you're copying are built from hundreds of dense rain-gauge/radar
    points. We only have ~20-40 monitored site coordinates, so this is a
    much coarser interpolation. It's visually legitimate (same technique:
    scattered-point interpolation -> filled contours) but the resolution
    is limited by how many/how densely-spaced your monitoring sites are.
    Adding more sites (more barangays) directly improves contour quality.
    """
    names = list(location_results.keys())
    if len(names) < 4:
        # Need at least a handful of points for interpolation to mean anything
        return None

    lats = np.array([location_results[n]["lat"] for n in names], dtype=float)
    lons = np.array([location_results[n]["lon"] for n in names], dtype=float)
    values = np.array([location_results[n].get(value_key, 0.0) for n in names], dtype=float)

    lat_min, lat_max = lats.min() - padding_deg, lats.max() + padding_deg
    lon_min, lon_max = lons.min() - padding_deg, lons.max() + padding_deg

    grid_lat, grid_lon = np.mgrid[
        lat_min:lat_max:complex(grid_res),
        lon_min:lon_max:complex(grid_res),
    ]

    # Cascade: cubic (smoothest) -> linear -> nearest, to fill any NaNs left
    # by cubic/linear outside the convex hull of the points.
    grid = griddata((lats, lons), values, (grid_lat, grid_lon), method="cubic")
    grid_lin = griddata((lats, lons), values, (grid_lat, grid_lon), method="linear")
    grid = np.where(np.isnan(grid), grid_lin, grid)
    grid_near = griddata((lats, lons), values, (grid_lat, grid_lon), method="nearest")
    grid = np.where(np.isnan(grid), grid_near, grid)
    grid = np.clip(grid, 0, 100)

    norm = mcolors.Normalize(vmin=0, vmax=100)

    fig, ax = plt.subplots(figsize=(grid_res / 100, grid_res / 100), dpi=100)
    ax.axis("off")
    fig.patch.set_alpha(0)
    ax.contourf(grid_lon, grid_lat, grid, levels=20, cmap=_CONTOUR_CMAP,
                norm=norm, alpha=0.55, antialiased=True)
    # thin contour lines on top, like isopleths on the NWS map
    ax.contour(grid_lon, grid_lat, grid, levels=10, colors="white",
               linewidths=0.3, alpha=0.35)
    ax.set_xlim(lon_min, lon_max)
    ax.set_ylim(lat_min, lat_max)
    fig.subplots_adjust(left=0, right=1, top=1, bottom=0)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", transparent=True, pad_inches=0)
    plt.close(fig)
    buf.seek(0)
    img_b64 = base64.b64encode(buf.read()).decode()

    bounds = [[lat_min, lon_min], [lat_max, lon_max]]
    return img_b64, bounds


def _add_contour_legend(fmap):
    legend_html = """
    <div style="
        position: fixed; bottom: 24px; left: 24px; z-index: 9999;
        background: rgba(15,23,42,0.9); color: #f0f6fc;
        border: 1px solid rgba(148,197,255,0.25); border-radius: 10px;
        padding: 10px 14px; font-family: Arial, sans-serif; font-size: 12px;
        box-shadow: 0 6px 20px rgba(0,0,0,0.35);">
        <b>Flash Flood Risk Contour</b><br>
        <div style="display:flex; align-items:center; margin-top:6px;">
            <div style="width:120px; height:10px; border-radius:4px;
                background: linear-gradient(90deg, #1e8f4e, #2ecc71, #f1c40f, #e67e22, #e74c3c, #8e1c1c);
                margin-right:8px;"></div>
        </div>
        <div style="display:flex; justify-content:space-between; width:120px; margin-top:2px;">
            <span>0</span><span>50</span><span>100</span>
        </div>
    </div>
    """
    fmap.get_root().html.add_child(folium.Element(legend_html))


def build_hazard_map(location_results: dict, center=(9.5, 122.5), zoom_start=6,
                      show_contour: bool = True, contour_value: str = "ffri"):
    """
    location_results: dict of {name: {"lat", "lon", "ffri", "risk_label",
                                       "risk_color", "elevation", ...}}
    show_contour: if True, adds an interpolated filled-contour layer
                  (NWS-style) underneath the site markers, toggleable via
                  the layer control in the top-right of the map.
    contour_value: which numeric field in location_results to interpolate.
                   Defaults to "ffri" (0-100 risk index). You could also
                   pass a per-site rainfall value if you add one.
    """
    fmap = folium.Map(
        location=center,
        zoom_start=zoom_start,
        tiles="CartoDB positron",
        control_scale=True,
    )
    Fullscreen(position="topright").add_to(fmap)
    fmap.get_root().header.add_child(folium.Element("""
        <style>
            html, body { height: 100% !important; width: 100% !important; margin: 0; padding: 0; }
            .folium-map { height: 100% !important; width: 100% !important; }
        </style>
    """))

    if show_contour:
        overlay = _build_contour_overlay_png(location_results, value_key=contour_value)
        if overlay is not None:
            img_b64, bounds = overlay
            contour_layer = folium.FeatureGroup(name="🌈 Risk Contour (interpolated)", show=True)
            folium.raster_layers.ImageOverlay(
                image=f"data:image/png;base64,{img_b64}",
                bounds=bounds,
                opacity=0.65,
                interactive=False,
                cross_origin=False,
            ).add_to(contour_layer)
            contour_layer.add_to(fmap)
            _add_contour_legend(fmap)

    markers_layer = folium.FeatureGroup(name="📍 Monitoring Sites", show=True)
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
        ).add_to(markers_layer)
        folium.Marker(
            location=(lat, lon),
            icon=folium.Icon(color="white", icon_color=color, icon="tint", prefix="fa"),
            tooltip=f"{name}: {label}",
        ).add_to(markers_layer)
    markers_layer.add_to(fmap)

    folium.LayerControl(collapsed=False).add_to(fmap)

    map_var = fmap.get_name()
    resize_fix = folium.Element(f"""
        <script>
            function __fixMapSize_{map_var}() {{
                if (typeof {map_var} !== "undefined") {{
                    {map_var}.invalidateSize({{ animate: false, pan: false }});
                }}
            }}
            setTimeout(__fixMapSize_{map_var}, 300);
            setTimeout(__fixMapSize_{map_var}, 900);
            window.addEventListener("load", __fixMapSize_{map_var});
        </script>
    """)
    fmap.get_root().html.add_child(resize_fix)
    return fmap
