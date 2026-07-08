import io
import base64

import numpy as np
import folium
from folium.plugins import Fullscreen
from scipy.interpolate import griddata
from scipy.spatial import ConvexHull
from matplotlib.path import Path as MplPath
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors


# Same color language as config.RISK_LEVELS (green -> yellow -> orange -> red),
# but split into 6 discrete bands so the map reads like a classic hazard-map
# poster (hard color edges) instead of a smooth continuous gradient.
_CONTOUR_COLORS = ["#1e8f4e", "#2ecc71", "#f1c40f", "#e67e22", "#e74c3c", "#8e1c1c"]
_DISCRETE_BOUNDS = [0, 16, 33, 50, 66, 83, 100.0001]
_DISCRETE_CMAP = mcolors.ListedColormap(_CONTOUR_COLORS)
_DISCRETE_NORM = mcolors.BoundaryNorm(_DISCRETE_BOUNDS, _DISCRETE_CMAP.N)

_LEGEND_ROWS = [
    ("#1e8f4e", "Low risk"),
    ("#2ecc71", "Slightly low risk"),
    ("#f1c40f", "Medium risk"),
    ("#e67e22", "Medium to high risk"),
    ("#e74c3c", "High risk"),
]


def _hull_mask(grid_lat, grid_lon, lats, lons, buffer_frac=0.18):
    """
    Boolean mask (same shape as grid_lat/grid_lon) that is True only inside
    a (buffered) convex hull of the monitored site coordinates.

    This is what makes the contour fill an irregular blob shaped roughly
    like the monitored area, instead of a plain rectangle — visually much
    closer to a real administrative-boundary hazard map (see reference).
    Since we don't have real municipal boundary polygons for arbitrary
    user-added sites, the convex hull is a reasonable stand-in "coverage
    shape" that always contains every monitored point.
    """
    pts = np.column_stack([lons, lats])

    if len(pts) < 3:
        # Not enough points for a hull — fall back to a circular buffer
        center = pts.mean(axis=0) if len(pts) else np.array([0.0, 0.0])
        extra = np.max(np.linalg.norm(pts - center, axis=1)) if len(pts) else 0.0
        r = buffer_frac + extra
        d = np.sqrt((grid_lon - center[0]) ** 2 + (grid_lat - center[1]) ** 2)
        return d <= r

    hull = ConvexHull(pts)
    hull_pts = pts[hull.vertices]
    centroid = hull_pts.mean(axis=0)
    # radially expand the hull outward a bit past the outermost sites
    buffered = centroid + (hull_pts - centroid) * (1.0 + buffer_frac)
    path = MplPath(buffered)
    grid_pts = np.column_stack([grid_lon.ravel(), grid_lat.ravel()])
    inside = path.contains_points(grid_pts)
    return inside.reshape(grid_lon.shape)


def _build_contour_overlay_png(location_results: dict, value_key: str = "ffri",
                                grid_res: int = 260, padding_deg: float = 1.0,
                                hull_buffer_frac: float = 0.18):
    """
    Interpolates a scalar field (default: FFRI) across the monitored sites and
    rasterizes it as a filled, hard-edged, hull-clipped contour PNG (base64) —
    the same visual language as an NWS/GIS-style hazard-zone map.

    IMPORTANT CAVEAT (say this in your defense if asked): a poster map like
    the one you're referencing is built from a full administrative-boundary
    shapefile + hundreds of dense rain-gauge/radar/DEM points. We only have
    ~20-40 monitored site coordinates and no municipal boundary polygons, so
    this is a coarser scattered-point interpolation clipped to the convex
    hull of your monitored sites (a stand-in "coverage shape"), not the
    actual district boundary. It's visually legitimate (same technique:
    scattered-point interpolation -> filled contour bands) but resolution
    and shape fidelity improve as you add more sites (more barangays) and,
    ideally, real boundary shapefiles.
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

    # Clip to the (buffered) convex hull of the monitored sites so the
    # overlay reads as a bounded "region" shape rather than a rectangle.
    mask = _hull_mask(grid_lat, grid_lon, lats, lons, buffer_frac=hull_buffer_frac)
    grid = np.where(mask, grid, np.nan)

    fig, ax = plt.subplots(figsize=(grid_res / 100, grid_res / 100), dpi=100)
    ax.axis("off")
    fig.patch.set_alpha(0)
    ax.contourf(grid_lon, grid_lat, grid, levels=_DISCRETE_BOUNDS, colors=_CONTOUR_COLORS,
                norm=_DISCRETE_NORM, alpha=0.85, antialiased=True)
    # thin white isopleth lines between bands, like the reference poster map
    ax.contour(grid_lon, grid_lat, grid, levels=_DISCRETE_BOUNDS, colors="white",
               linewidths=0.5, alpha=0.55)
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
    rows_html = "".join(
        f"""<div style="display:flex; align-items:center; margin:3px 0;">
                <span style="width:16px; height:16px; background:{color};
                    border-radius:3px; margin-right:8px; display:inline-block;
                    border:1px solid rgba(255,255,255,0.25);"></span>{label}
            </div>"""
        for color, label in _LEGEND_ROWS
    )
    legend_html = f"""
    <div style="
        position: fixed; bottom: 24px; left: 24px; z-index: 9999;
        background: rgba(15,23,42,0.92); color: #f0f6fc;
        border: 1px solid rgba(148,197,255,0.25); border-radius: 10px;
        padding: 12px 16px; font-family: Arial, sans-serif; font-size: 12.5px;
        box-shadow: 0 6px 20px rgba(0,0,0,0.35); min-width: 175px;">
        <b style="font-size:13.5px;">Flood risk level</b>
        <div style="margin-top:8px;">
            {rows_html}
        </div>
    </div>
    """
    fmap.get_root().html.add_child(folium.Element(legend_html))


def _add_north_arrow(fmap):
    html = """
    <div style="
        position: fixed; top: 100px; left: 20px; z-index: 9999;
        background: rgba(15,23,42,0.85); border-radius: 8px; padding: 6px 10px;
        text-align:center; color:#f0f6fc; font-family: Arial, sans-serif;
        box-shadow: 0 4px 14px rgba(0,0,0,0.3); line-height:1;">
        <div style="font-size:18px;">▲</div>
        <div style="font-weight:bold; font-size:13px; margin-top:2px;">N</div>
    </div>
    """
    fmap.get_root().html.add_child(folium.Element(html))


def _add_site_labels(fmap, location_results):
    """
    Always-visible bold site-name labels (white halo, dark text) sitting
    just above each marker — the same "always-on" label style used for the
    district names in the reference hazard-map poster, instead of a
    hover-only tooltip.
    """
    labels_layer = folium.FeatureGroup(name="🏷️ Site Labels", show=True)
    for name, info in location_results.items():
        lat, lon = info["lat"], info["lon"]
        label_html = f"""
        <div style="
            font-family: Arial, sans-serif; font-weight:700; font-size:12px;
            color:#0b1220; white-space:nowrap; pointer-events:none;
            text-shadow: -1px -1px 0 #fff, 1px -1px 0 #fff,
                         -1px 1px 0 #fff, 1px 1px 0 #fff, 0 0 4px #fff;
            transform: translate(-50%, -145%);">
            {name}
        </div>
        """
        folium.Marker(
            location=(lat, lon),
            icon=folium.DivIcon(html=label_html, icon_size=(0, 0), icon_anchor=(0, 0)),
        ).add_to(labels_layer)
    labels_layer.add_to(fmap)


def build_hazard_map(location_results: dict, center=(9.5, 122.5), zoom_start=6,
                      show_contour: bool = True, contour_value: str = "ffri"):
    """
    location_results: dict of {name: {"lat", "lon", "ffri", "risk_label",
                                       "risk_color", "elevation", ...}}
    show_contour: if True, adds an interpolated filled-contour layer
                  (hull-clipped, hard-edged bands, hazard-map poster style)
                  underneath the site markers, toggleable via the layer
                  control in the top-right of the map.
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
                opacity=0.8,
                interactive=False,
                cross_origin=False,
            ).add_to(contour_layer)
            contour_layer.add_to(fmap)
            _add_contour_legend(fmap)
            _add_north_arrow(fmap)

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

    # Permanent site-name labels (like the reference poster's district labels)
    _add_site_labels(fmap, location_results)

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
