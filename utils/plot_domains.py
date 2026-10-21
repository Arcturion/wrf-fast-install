#!/usr/bin/env python3
"""Plot the nested domains from a namelist.wps BEFORE running WRF/WPS.

Catches domain mistakes (wrong centre, child outside parent, wrong ratio)
for free. Supported map_proj values: lambert, mercator, lat-lon.
Positions are a preview-grade computation on a spherical earth
(R = 6370 km, the WRF value): good for checking placement and nesting,
not a replacement for geogrid.exe output.

Usage:
    python plot_domains.py namelist.wps
    python plot_domains.py namelist.wps --out domains.png
"""

from __future__ import annotations

import argparse
import math
import re

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from common import make_map_ax

R_EARTH = 6370000.0  # WRF spherical earth radius, m


# --------------------------------------------------------------------------- #
# namelist parsing (only the &geogrid section is needed)
# --------------------------------------------------------------------------- #
def parse_geogrid(path: str) -> dict[str, list]:
    text = open(path).read()
    m = re.search(r"&geogrid(.*?)(\n\s*/|\Z)", text, re.S | re.I)
    if not m:
        raise SystemExit("No &geogrid section found in the namelist")
    body = m.group(1)
    out: dict[str, list] = {}
    for key, raw in re.findall(r"(\w+)\s*=\s*([^/&]+?)(?=\n\s*\w+\s*=|\Z)",
                               body, re.S):
        vals = [v.strip().strip("'\"") for v in raw.split(",") if v.strip()]
        parsed = []
        for v in vals:
            try:
                parsed.append(float(v))
            except ValueError:
                parsed.append(v)
        out[key.lower()] = parsed
    return out


def _get(cfg: dict, key: str, idx: int, default=None):
    vals = cfg.get(key)
    if not vals:
        return default
    return vals[idx] if idx < len(vals) else vals[0]


# --------------------------------------------------------------------------- #
# Projections on a sphere. In both classes the reference point maps to
# exactly (0, 0) in projected metres.
# --------------------------------------------------------------------------- #
class Lambert:
    """Spherical Lambert conformal conic.

    Southern-hemisphere cones (negative truelats, negative cone constant)
    are handled by mirroring: the projection is computed for the mirrored
    (northern) latitudes and the y axis is flipped back afterwards. A naive
    signed implementation gets the inverse longitude wrong by pi / n,
    because a negative rho flips both atan2 arguments in the inverse.
    """

    def __init__(self, ref_lat, ref_lon, truelat1, truelat2, stand_lon):
        self.mirror = truelat1 < 0
        s = -1.0 if self.mirror else 1.0
        la1, la2 = math.radians(s * truelat1), math.radians(s * truelat2)
        if abs(truelat1 - truelat2) < 1e-6:
            self.n = math.sin(la1)
        else:
            self.n = (math.log(math.cos(la1) / math.cos(la2)) /
                      math.log(math.tan(math.pi / 4 + la2 / 2) /
                               math.tan(math.pi / 4 + la1 / 2)))
        self.F = (math.cos(la1) * math.tan(math.pi / 4 + la1 / 2) ** self.n
                  / self.n)
        self.lon0 = math.radians(stand_lon)
        self.rho_ref = self._rho(math.radians(s * ref_lat))

    def _rho(self, phi):
        return R_EARTH * self.F / math.tan(math.pi / 4 + phi / 2) ** self.n

    def _forward_core(self, lat, lon):
        phi, lam = math.radians(lat), math.radians(lon)
        rho = self._rho(phi)
        theta = self.n * (lam - self.lon0)
        return rho * math.sin(theta), self.rho_ref - rho * math.cos(theta)

    def _inverse_core(self, x, y):
        dy = self.rho_ref - y
        rho = math.hypot(x, dy)
        theta = math.atan2(x, dy)
        phi = (2 * math.atan((R_EARTH * self.F / rho) ** (1 / self.n))
               - math.pi / 2)
        lam = self.lon0 + theta / self.n
        return math.degrees(phi), math.degrees(lam)

    def forward(self, lat, lon):
        if self.mirror:
            x, y = self._forward_core(-lat, lon)
            return x, -y
        return self._forward_core(lat, lon)

    def inverse(self, x, y):
        if self.mirror:
            la, lo = self._inverse_core(x, -y)
            return -la, lo
        return self._inverse_core(x, y)


class Mercator:
    """Spherical Mercator with the reference point at (0, 0)."""

    def __init__(self, ref_lat, ref_lon):
        self.lon_ref = math.radians(ref_lon)
        self.y_ref = self._y(math.radians(ref_lat))

    @staticmethod
    def _y(phi):
        return R_EARTH * math.log(math.tan(math.pi / 4 + phi / 2))

    def forward(self, lat, lon):
        return (R_EARTH * (math.radians(lon) - self.lon_ref),
                self._y(math.radians(lat)) - self.y_ref)

    def inverse(self, x, y):
        phi = 2 * math.atan(math.exp((y + self.y_ref) / R_EARTH)) - math.pi / 2
        lam = self.lon_ref + x / R_EARTH
        return math.degrees(phi), math.degrees(lam)


# --------------------------------------------------------------------------- #
def compute_domains(cfg: dict) -> list[dict]:
    """Compute every domain's border, centre and corners in lat/lon."""
    map_proj = str(_get(cfg, "map_proj", 0, "lambert")).lower()
    ref_lat = float(_get(cfg, "ref_lat", 0))
    ref_lon = float(_get(cfg, "ref_lon", 0))
    stand_lon = float(_get(cfg, "stand_lon", 0, ref_lon))
    truelat1 = float(_get(cfg, "truelat1", 0, ref_lat))
    truelat2 = float(_get(cfg, "truelat2", 0, truelat1))
    n_dom = len(cfg.get("e_we", []))
    if n_dom == 0:
        raise SystemExit("namelist.wps has no e_we in &geogrid")

    if map_proj == "lambert":
        proj = Lambert(ref_lat, ref_lon, truelat1, truelat2, stand_lon)
    elif map_proj == "mercator":
        proj = Mercator(ref_lat, ref_lon)
    elif map_proj in ("lat-lon", "latlon", "regular_ll"):
        proj = None
    else:
        raise SystemExit(f"map_proj {map_proj!r} not supported by this preview "
                         "tool (lambert, mercator, lat-lon are)")

    domains: list[dict] = []
    grids: dict[int, tuple] = {}  # d -> (xs, ys, dx) projected m, or degrees
    for d in range(n_dom):
        e_we = int(_get(cfg, "e_we", d))
        e_sn = int(_get(cfg, "e_sn", d))
        n_we, n_sn = e_we - 1, e_sn - 1  # mass points
        if d == 0:
            dx = float(_get(cfg, "dx", 0))
            dy = float(_get(cfg, "dy", 0, dx))
            xs = (np.arange(n_we) - (n_we - 1) / 2.0) * dx
            ys = (np.arange(n_sn) - (n_sn - 1) / 2.0) * dy
        else:
            parent = int(_get(cfg, "parent_id", d, 1)) - 1
            ratio = float(_get(cfg, "parent_grid_ratio", d, 1))
            pxs, pys, pdx = grids[parent]
            dx = pdx / ratio
            dy = dx
            i0 = int(_get(cfg, "i_parent_start", d, 1)) - 1
            j0 = int(_get(cfg, "j_parent_start", d, 1)) - 1
            if not (0 <= i0 < len(pxs) and 0 <= j0 < len(pys)):
                raise SystemExit(
                    f"domain {d + 1}: i/j_parent_start outside the parent grid")
            xs = pxs[i0] + np.arange(n_we) * dx
            ys = pys[j0] + np.arange(n_sn) * dy
        grids[d] = (xs, ys, dx)

        if proj is None:  # lat-lon: xs/ys are degree offsets from ref
            lons = ref_lon + xs
            lats = ref_lat + ys
            border_lon = np.concatenate(
                [lons, np.full(n_sn, lons[-1]), lons[::-1],
                 np.full(n_sn, lons[0])])
            border_lat = np.concatenate(
                [np.full(n_we, lats[0]), lats,
                 np.full(n_we, lats[-1]), lats[::-1]])
            centre = (float(lats[n_sn // 2]), float(lons[n_we // 2]))
            sw = (float(lats[0]), float(lons[0]))
            ne = (float(lats[-1]), float(lons[-1]))
            width_km = float((lons[-1] - lons[0]) * 111.32
                             * math.cos(math.radians(ref_lat)))
            height_km = float((lats[-1] - lats[0]) * 110.57)
            dx_label = f"{dx:g} deg"
        else:
            border = _perimeter(xs, ys, proj)
            border_lat, border_lon = border
            centre = proj.inverse(float(xs[n_we // 2]), float(ys[n_sn // 2]))
            sw = proj.inverse(float(xs[0]), float(ys[0]))
            ne = proj.inverse(float(xs[-1]), float(ys[-1]))
            width_km = float(xs[-1] - xs[0]) / 1000.0
            height_km = float(ys[-1] - ys[0]) / 1000.0
            dx_label = f"{dx / 1000.0:g} km"

        domains.append({
            "index": d + 1,
            "n_we": n_we, "n_sn": n_sn,
            "dx_label": dx_label,
            "width_km": width_km, "height_km": height_km,
            "centre": centre, "sw": sw, "ne": ne,
            "border_lat": border_lat, "border_lon": border_lon,
            "xs": xs, "ys": ys,
        })
    return {"map_proj": map_proj, "ref": (ref_lat, ref_lon),
            "domains": domains}


def _perimeter(xs, ys, proj, samples: int = 25):
    pts = []
    for x in np.linspace(xs[0], xs[-1], samples):
        pts.append((x, ys[0]))
    for y in np.linspace(ys[0], ys[-1], samples):
        pts.append((xs[-1], y))
    for x in np.linspace(xs[-1], xs[0], samples):
        pts.append((x, ys[-1]))
    for y in np.linspace(ys[-1], ys[0], samples):
        pts.append((xs[0], y))
    lats, lons = zip(*(proj.inverse(float(x), float(y)) for x, y in pts))
    return np.array(lats), np.array(lons)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("namelist", help="path to namelist.wps")
    ap.add_argument("--out", default="domains.png", help="output PNG")
    args = ap.parse_args()

    cfg = parse_geogrid(args.namelist)
    result = compute_domains(cfg)
    domains = result["domains"]
    print(f"map_proj={result['map_proj']}  ref={result['ref']}  "
          f"domains={len(domains)}")
    for dom in domains:
        print(f"d0{dom['index']}: {dom['n_we']} x {dom['n_sn']} mass points, "
              f"dx={dom['dx_label']}, size {dom['width_km']:.0f} x "
              f"{dom['height_km']:.0f} km, centre "
              f"({dom['centre'][0]:.3f}, {dom['centre'][1]:.3f}), "
              f"SW ({dom['sw'][0]:.3f}, {dom['sw'][1]:.3f}), "
              f"NE ({dom['ne'][0]:.3f}, {dom['ne'][1]:.3f})")

    fig, ax, using_cartopy = make_map_ax(figsize=(10, 9))
    if not using_cartopy:
        print("note: cartopy not installed -- plain lat/lon map, no coastlines")
    colours = plt.cm.tab10.colors
    for dom in domains:
        c = colours[(dom["index"] - 1) % len(colours)]
        kw = {}
        if using_cartopy:
            import cartopy.crs as ccrs
            kw["transform"] = ccrs.PlateCarree()
        ax.plot(dom["border_lon"], dom["border_lat"], color=c, linewidth=1.6,
                label=f"d0{dom['index']}", **kw)
        ax.plot(dom["centre"][1], dom["centre"][0], "+", color=c,
                markersize=11, **kw)
    ax.legend(title="domains")
    ax.set_title(f"WRF domains from {args.namelist} ({result['map_proj']})")
    fig.savefig(args.out, dpi=150, bbox_inches="tight")
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
