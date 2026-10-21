#!/usr/bin/env python3
"""Inspect a WRF run at a glance: files, times, grid, projection, variables.

Usage:
    python inspect_wrf.py 'wrfout_d01_*'
    python inspect_wrf.py 'wrfout_d02_*' --full
"""

from __future__ import annotations

import argparse

import numpy as np

from common import find_files, get_latlon, get_times, open_wrf


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pattern", help="glob pattern for wrfout files, e.g. 'wrfout_d01_*'")
    ap.add_argument("--full", action="store_true",
                    help="list every variable (default: summary counts only)")
    args = ap.parse_args()

    files = find_files(args.pattern)
    ds = open_wrf(args.pattern)
    times = get_times(ds)
    lat, lon = get_latlon(ds)

    print(f"Files          : {len(files)}")
    for f in files:
        print(f"                   {f}")
    print(f"Times          : {len(times)} steps, {times[0]} -> {times[-1]}")
    if len(times) > 1:
        steps = np.diff(times.values).astype("timedelta64[s]").astype(float)
        uniq = sorted(set(steps))
        print(f"Output interval: {uniq} s" if len(uniq) > 1
              else f"Output interval: {uniq[0]:.0f} s")
    print(f"Grid           : {lat.shape[0]} x {lat.shape[1]} "
          f"(south_north x west_east)")
    print(f"Lat range      : {lat.min():.3f} .. {lat.max():.3f}")
    print(f"Lon range      : {lon.min():.3f} .. {lon.max():.3f}")

    attrs = ds.attrs
    if attrs:
        print("Global attributes:")
        for key in ("TITLE", "START_DATE", "SIMULATION_START_DATE", "DX", "DY",
                    "CEN_LAT", "CEN_LON", "MAP_PROJ", "TRUELAT1", "TRUELAT2",
                    "STAND_LON", "WEST-EAST_GRID_DIMENSION",
                    "SOUTH-NORTH_GRID_DIMENSION", "BOTTOM-TOP_GRID_DIMENSION"):
            if key in attrs:
                print(f"  {key:28s} {attrs[key]}")

    groups: dict[int, list[str]] = {}
    for name, var in ds.data_vars.items():
        groups.setdefault(len(var.dims), []).append(name)
    print("Variables:")
    for ndim in sorted(groups):
        names = sorted(groups[ndim])
        print(f"  {ndim}D ({len(names)}): {', '.join(names) if args.full else ', '.join(names[:12]) + (' ...' if len(names) > 12 else '')}")
    print(f"Total variables: {sum(len(v) for v in groups.values())}")
    ds.close()


if __name__ == "__main__":
    main()
