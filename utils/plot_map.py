#!/usr/bin/env python3
"""Plot any wrfout variable on a map and save it as a PNG.

Uses the file's own XLAT/XLONG. With cartopy installed you get coastlines
and borders; without it, a plain lat/lon map is drawn (and a note printed).

Variable shortcuts: RAIN (accumulated total), RAIN_INTERVAL (rain in the
output step ending at the selected time), WS10 (10 m wind speed). Any other
name is taken as the raw variable; 3-D variables need --level (index of the
bottom_top level, default 0).

Usage:
    python plot_map.py 'wrfout_d01_*'                       # interval rain, last step
    python plot_map.py 'wrfout_d01_*' --var T2 --time '2024-11-17 05:00'
    python plot_map.py 'wrfout_d01_*' --var RAIN --time-index 10 --vmax 100
    python plot_map.py 'wrfout_d01_*' --var U --level 5 --out u500.png
"""

from __future__ import annotations

import argparse

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from common import (decumulate, get_latlon, get_times, make_map_ax, open_wrf,
                    plot_field, resolve_var, select_time_index, total_rain)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pattern", help="glob pattern for wrfout files, e.g. 'wrfout_d01_*'")
    ap.add_argument("--var", default="RAIN_INTERVAL",
                    help="variable name or shortcut (default RAIN_INTERVAL)")
    ap.add_argument("--time-index", type=int, default=None,
                    help="positional time index (negative counts from the end)")
    ap.add_argument("--time", default=None,
                    help="timestamp 'YYYY-MM-DD HH:MM' (nearest step is used)")
    ap.add_argument("--level", type=int, default=0,
                    help="bottom_top level index for 3-D variables (default 0)")
    ap.add_argument("--out", default=None, help="output PNG (default derived)")
    ap.add_argument("--cmap", default=None, help="matplotlib colormap")
    ap.add_argument("--vmin", type=float, default=None)
    ap.add_argument("--vmax", type=float, default=None)
    ap.add_argument("--title", default=None)
    args = ap.parse_args()

    ds = open_wrf(args.pattern)
    times = get_times(ds)
    idx = select_time_index(ds, args.time_index, args.time)
    lat, lon = get_latlon(ds)

    key = args.var.upper()
    if key == "RAIN_INTERVAL":
        field = decumulate(total_rain(ds)).isel(Time=idx)
        label = "interval rain (mm)"
        cmap = args.cmap or "Blues"
    else:
        var = resolve_var(ds, args.var)
        field = var.isel(Time=idx)
        if "bottom_top" in field.dims:
            field = field.isel(bottom_top=args.level)
        # drop any remaining non-grid dims of size 1 (e.g. soil layers handled
        # by user via raw names are squeezed only when singleton)
        for d in list(field.dims):
            if d not in ("south_north", "west_east") and field.sizes[d] == 1:
                field = field.isel({d: 0})
        units = field.attrs.get("units", "")
        label = f"{args.var} ({units})" if units else args.var
        cmap = args.cmap or "viridis"

    values = np.asarray(field.values, dtype=float)
    if values.ndim != 2:
        raise SystemExit(f"Variable {args.var} at this time has shape "
                         f"{values.shape}; expected a 2-D field")

    out = args.out or f"{args.var.lower()}_{times[idx].strftime('%Y%m%d_%H%M')}.png"
    fig, ax, using_cartopy = make_map_ax()
    if not using_cartopy:
        print("note: cartopy not installed -- plain lat/lon map, no coastlines")
    mesh = plot_field(ax, lon, lat, values, using_cartopy,
                      cmap=cmap, vmin=args.vmin, vmax=args.vmax)
    fig.colorbar(mesh, ax=ax, shrink=0.7, label=label)
    ax.set_title(args.title or
                 f"{label} — {times[idx].strftime('%Y-%m-%d %H:%M UTC')}")
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"Wrote {out}  (time index {idx}, {times[idx]})")
    ds.close()


if __name__ == "__main__":
    main()
