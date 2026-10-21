#!/usr/bin/env python3
"""Animate a wrfout variable over time into a GIF (or MP4 if ffmpeg exists).

Default is interval rain per output step. Colour limits are fixed across
frames (default: 99th percentile of all frames) so frames are comparable.

Usage:
    python animate.py 'wrfout_d01_*'
    python animate.py 'wrfout_d01_*' --var T2 --fps 4 --out t2.gif
    python animate.py 'wrfout_d01_*' --var RAIN --accumulated --vmax 150
"""

from __future__ import annotations

import argparse
import shutil

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.animation import FFMpegWriter, FuncAnimation, PillowWriter

from common import (decumulate, get_latlon, get_times, make_map_ax, open_wrf,
                    plot_field, resolve_var, total_rain)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pattern", help="glob pattern for wrfout files, e.g. 'wrfout_d01_*'")
    ap.add_argument("--var", default="RAIN_INTERVAL",
                    help="variable or shortcut (default RAIN_INTERVAL)")
    ap.add_argument("--accumulated", action="store_true",
                    help="for --var RAIN_INTERVAL, animate accumulated rain instead")
    ap.add_argument("--level", type=int, default=0,
                    help="bottom_top level index for 3-D variables (default 0)")
    ap.add_argument("--out", default="animation.gif", help="output .gif or .mp4")
    ap.add_argument("--fps", type=int, default=2)
    ap.add_argument("--cmap", default=None)
    ap.add_argument("--vmin", type=float, default=None)
    ap.add_argument("--vmax", type=float, default=None)
    args = ap.parse_args()

    ds = open_wrf(args.pattern)
    times = get_times(ds)
    lat, lon = get_latlon(ds)

    key = args.var.upper()
    if key in ("RAIN_INTERVAL", "RAIN"):
        accum = total_rain(ds)
        field = accum if (key == "RAIN" or args.accumulated) else decumulate(accum)
        label = "accumulated rain (mm)" if (key == "RAIN" or args.accumulated) \
            else "interval rain (mm)"
        cmap = args.cmap or "Blues"
    else:
        var = resolve_var(ds, args.var)
        if "bottom_top" in var.dims:
            var = var.isel(bottom_top=args.level)
        field = var
        units = var.attrs.get("units", "")
        label = f"{args.var} ({units})" if units else args.var
        cmap = args.cmap or "viridis"

    values = np.asarray(field.values, dtype=float)
    if values.ndim != 3:
        raise SystemExit(f"Expected a (Time, south_north, west_east) field, "
                         f"got shape {values.shape}")
    vmin = args.vmin if args.vmin is not None else float(np.nanmin(values))
    vmax = args.vmax if args.vmax is not None else float(np.nanpercentile(values, 99))
    if vmax <= vmin:
        vmax = vmin + 1.0

    fig, ax, using_cartopy = make_map_ax()
    if not using_cartopy:
        print("note: cartopy not installed -- plain lat/lon map, no coastlines")
    mesh = plot_field(ax, lon, lat, values[0], using_cartopy,
                      cmap=cmap, vmin=vmin, vmax=vmax)
    fig.colorbar(mesh, ax=ax, shrink=0.7, label=label)
    title = ax.set_title("")

    def update(k):
        mesh.set_array(np.asarray(values[k]).ravel())
        title.set_text(f"{label} — {times[k].strftime('%Y-%m-%d %H:%M UTC')}")
        return mesh, title

    anim = FuncAnimation(fig, update, frames=values.shape[0], blit=False)
    if args.out.lower().endswith(".mp4"):
        if not shutil.which("ffmpeg"):
            raise SystemExit("ffmpeg not found for MP4 output; use a .gif output name")
        writer = FFMpegWriter(fps=args.fps)
    else:
        writer = PillowWriter(fps=args.fps)
    anim.save(args.out, writer=writer)
    print(f"Wrote {args.out} ({values.shape[0]} frames at {args.fps} fps, "
          f"colour range {vmin:.2f}..{vmax:.2f})")
    ds.close()


if __name__ == "__main__":
    main()
