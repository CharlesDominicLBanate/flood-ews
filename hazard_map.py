import io
import os
import json
import base64

import numpy as np
import folium
from folium.plugins import Fullscreen
from scipy.interpolate import griddata
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

# Philippines province/district (ADM2) boundaries, sourced from geoBoundaries CGAZ
# and filtered to shapeGroup == "PHL". Ship this file alongside the module.
# Attribution: geoBoundaries (Runfola et al., 2020), CC-BY 4.0.
_DEFAULT_BOUNDARY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ph_provinces.geojson")


# ---------------------------------------------------------------------------
# Real boundary geometry helpers (pure numpy + matplotlib.path, no shapely
# dependency needed)
# ---------------------------------------------------------------------------

def _load_province_boundaries(path=_DEFAULT_BOUNDARY_PATH):
    """
    Loads the Philippines province/district boundary GeoJSON.
    Returns a list of {"name": str, "geometry": geojson-geometry-dict}, or None
    if the file isn't found (caller should fall back gracefully in that case).
    """
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None

    provinces = []
    for feat in data.get("features", []):
        name = feat.get("properties", {}).get("shapeName", "Unknown")
        geometry = feat.get("geometry")
        if geometry:
            provinces.append({"name": name, "geometry": geometry})
    return provinces or None


def _polygon_rings(geometry):
    """
    Yields (exterior_ring, [hole_rings...]) tuples for a GeoJSON Polygon or
    MultiPolygon geometry. Rings are lists of [lon, lat] pairs.
    """
    gtype = geometry.get("type")
    coords = geometry.get("coordinates", [])
    if gtype == "Polygon":
        polys = [coords]
    elif gtype == "MultiPolygon":
        polys = coords
    else:
        return
    for poly in polys:
        if not poly:
            continue
        yield poly[0], poly[1:]


def _points_in_geometry(geometry, xs, ys):
    """
    Vectorized point-in-polygon test for a GeoJSON Polygon/MultiPolygon.
    Handles holes explicitly: a point counts as inside if it's inside some
    exterior ring and NOT inside any of that same polygon's holes.
    xs, ys: flat arrays of lon/lat. Returns a boolean array, same length.
    """
    pts = np.column_stack([xs, ys])
    inside = np.zeros(len(pts), dtype=bool)
    for exterior, holes in _polygon_rings(geometry):
        in_ext = MplPath(exterior).contains_points(pts)
        for hole in holes:
            in_ext &= ~MplPath(hole).contains_points(pts)
        inside |= in_ext
    return inside


def _assign_sites_to_provinces(location_results, provinces):
    """
    For each monitored site, finds which province polygon contains it.
    Returns dict {province_name: [site_name, ...]}. Sites that don't fall
    inside any known polygon (e.g. slightly offshore coordinates) are
    snapped to the nearest province centroid-ish match instead of dropped.
    """
    assignment = {}
    unmatched = []
    for name, info in location_results.items():
        lat, lon = info["lat"], info["lon"]
        matched = False
        for prov in provinces:
            if _points_in_geometry(prov["geometry"], np.array([lon]), np.array([lat]))[0]:
                assignment.setdefault(prov["name"], []).append(name)
                matched = True
                break
        if not matched:
            unmatched.append((name, lat, lon))

    # Snap unmatched (e.g. coastal) sites to the nearest province by distance
    # to that province's vertex closest to the point, so no site gets silently
    # dropped from the choropleth just for sitting a hair outside the coastline.
    if unmatched:
        for name, lat, lon in unmatched:
            best_prov, best_dist = None, np.inf
            for prov in provinces:
                for exterior, _holes in _polygon_rings(prov["geometry"]):
                    arr = np.asarray(exterior)
                    d = np.min((arr[:, 0] - lon) ** 2 + (arr[:, 1] - lat) ** 2)
                    if d < best_dist:
                        best_dist, best_prov = d, prov["name"]
            if best_prov:
                assignment.setdefault(best_prov, []).append(name)

    return assignment


def _covered_provinces_mask(provinces, covered_names, grid_lon, grid_lat):
    """
    Boolean mask over the grid: True inside the union of the named provinces'
    REAL polygons (coastlines, borders, and all). This is what makes the fill
    hug the actual shape of the monitored area instead of a smooth blob.
    """
    xs = grid_lon.ravel()
    ys = grid_lat.ravel()
    mask = np.zeros(xs.shape, dtype=bool)
    for prov in provinces:
        if prov["name"] not in covered_names:
            continue
        mask |= _points_in_geometry(prov["geometry"], xs, ys)
    return mask.reshape(grid_lon.shape)


def _hull_mask_fallback(grid_lat, grid_lon, lats, lons, buffer_frac=0.18):
    """
    Convex-hull fallback, used only if no boundary GeoJSON is available.
    Kept so the map still renders (just less accurately) in that situation.
    """
    from scipy.spatial import ConvexHull

    pts = np.column_stack([lons, lats])
    if len(pts) < 3:
        center = pts.mean(axis=0) if len(pts) else np.array([0.0, 0.0])
        extra = np.max(np.linalg.norm(pts - center, axis=1)) if len(pts) else 0.0
        r = buffer_frac + extra
        d = np.sqrt((grid_lon - center[0]) ** 2 + (grid_lat - center[1]) ** 2)
        return d <= r

    hull = ConvexHull(pts)
    hull_pts = pts[hull.vertices]
    centroid = hull_pts.mean(axis=0)
    buffered = centroid + (hull_pts - centroid) * (1.0 + buffer_frac)
    path = MplPath(buffered)
    grid_pts = np.column_stack([grid_lon.ravel(), grid_lat.ravel()])
    inside = path.contains_points(grid_pts)
    return inside.reshape(grid_lon.shape)


# ---------------------------------------------------------------------------
# Contour overlay
# ---------------------------------------------------------------------------

def _build_contour_overlay_png(location_results: dict, value_key: str = "ffri",
                                grid_res: int = 320, padding_deg: float = 0.6,
                                boundary_path: str = _DEFAULT_BOUNDARY_PATH):
    """
    Interpolates a scalar field (default: FFRI) across the monitored sites and
    rasterizes it as a filled, hard-edged contour PNG (base64), clipped to the
    REAL province/coastline boundaries of whichever provinces contain a
    monitored site -- instead of a smooth convex-hull blob. This is what gives
    the map the same "follows the actual land shape" look as an official
    NWS/MGB-style hazard-zone poster.

    Returns (img_b64, bounds, covered_provinces) or None if there isn't enough
    data to interpolate, or (img_b64, bounds, None) if the boundary file
    wasn't available and we fell back to the old convex-hull method.
    """
    names = list(location_results.keys())
    if len(names) < 4:
        return None

    lats = np.array([location_results[n]["lat"] for n in names], dtype=float)
    lons = np.array([location_results[n]["lon"] for n in names], dtype=float)
    values = np.array([location_results[n].get(value_key, 0.0) for n in names], dtype=float)

    provinces = _load_province_boundaries(boundary_path)
    covered_names = None

    if provinces:
        assignment = _assign_sites_to_provinces(location_results, provinces)
        covered_names = set(assignment.keys())
        # Bounding box = bounding box of only the covered provinces (plus a
        # small padding), so we don't waste resolution rendering the whole
        # archipelago when only a handful of provinces have data.
        lat_min, lat_max, lon_min, lon_max = 90.0, -90.0, 180.0, -180.0
        for prov in provinces:
            if prov["name"] not in covered_names:
                continue
            for exterior, _holes in _polygon_rings(prov["geometry"]):
                arr = np.asarray(exterior)
                lon_min = min(lon_min, arr[:, 0].min())
                lon_max = max(lon_max, arr[:, 0].max())
                lat_min = min(lat_min, arr[:, 1].min())
                lat_max = max(lat_max, arr[:, 1].max())
        lat_min -= padding_deg
        lat_max += padding_deg
        lon_min -= padding_deg
        lon_max += padding_deg
    else:
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

    if provinces:
        mask = _covered_provinces_mask(provinces, covered_names, grid_lon, grid_lat)
    else:
        mask = _hull_mask_fallback(grid_lat, grid_lon, lats, lons)
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
    return img_b64, bounds, (provinces, covered_names)


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


def _add_province_borders(fmap, provinces, covered_names):
    """
    Draws thin real province/coastline border lines under the risk fill --
    the same crisp administrative-boundary lines visible in the reference
    poster map, instead of leaving the coverage area borderless.
    """
    if not provinces or not covered_names:
        return
    features = [
        {"type": "Feature", "properties": {"name": p["name"]}, "geometry": p["geometry"]}
        for p in provinces if p["name"] in covered_names
    ]
    if not features:
        return
    borders_layer = folium.FeatureGroup(name="🗺️ Province Boundaries", show=True)
    folium.GeoJson(
        {"type": "FeatureCollection", "features": features},
        style_function=lambda feat: {
            "fillOpacity": 0,
            "color": "#1f2937",
            "weight": 1.1,
            "opacity": 0.6,
        },
        tooltip=folium.GeoJsonTooltip(fields=["name"], aliases=["Province:"]),
    ).add_to(borders_layer)
    borders_layer.add_to(fmap)


def build_hazard_map(location_results: dict, center=(9.5, 122.5), zoom_start=6,
                      show_contour: bool = True, contour_value: str = "ffri",
                      boundary_path: str = _DEFAULT_BOUNDARY_PATH):
    """
    location_results: dict of {name: {"lat", "lon", "ffri", "risk_label",
                                       "risk_color", "elevation", ...}}
    show_contour: if True, adds an interpolated filled-contour layer clipped
                  to the real province/coastline boundaries of the monitored
                  area (hard-edged bands, hazard-map poster style) underneath
                  the site markers, toggleable via the layer control.
    contour_value: which numeric field in location_results to interpolate.
                   Defaults to "ffri" (0-100 risk index).
    boundary_path: path to the Philippines province boundary GeoJSON. Falls
                   back to a convex-hull blob (old behavior) if not found.
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
        overlay = _build_contour_overlay_png(location_results, value_key=contour_value,
                                              boundary_path=boundary_path)
        if overlay is not None:
            img_b64, bounds, boundary_info = overlay
            contour_layer = folium.FeatureGroup(name="🌈 Risk Contour (interpolated)", show=True)
            folium.raster_layers.ImageOverlay(
                image=f"data:image/png;base64,{img_b64}",
                bounds=bounds,
                opacity=0.8,
                interactive=False,
                cross_origin=False,
            ).add_to(contour_layer)
            contour_layer.add_to(fmap)

            if boundary_info is not None:
                provinces, covered_names = boundary_info
                _add_province_borders(fmap, provinces, covered_names)

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
