#!/usr/bin/env python3
"""Subset wrfout files by a lat/lon box and/or a time range into one NetCDF.

The box is applied on the file's own XLAT/XLONG: the smallest index ranges
whose cells fall inside the requested box are kept (the kept region can be
slightly larger than the box on a curvilinear grid).

Usage:
    python subset_wrf.py 'wrfout_d01_*' --lat-min -7 --lat-max -5 \
        --lon-min 105 --lon-max 108 --out jakarta_box.nc
    python subset_wrf.py 'wrfout_d01_*' --start '2024-11-17 03:00' \
        --end '2024-11-17 12:00' --out morning.nc
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from common import get_latlon, get_times, open_wrf


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pattern", help="glob pattern for wrfout files, e.g. 'wrfout_d01_*'")
    ap.add_argument("--lat-min", type=float, default=None)
    ap.add_argument("--lat-max", type=float, default=None)
    ap.add_argument("--lon-min", type=float, default=None)
    ap.add_argument("--lon-max", type=float, default=None)
    ap.add_argument("--start", default=None, help="first time to keep, 'YYYY-MM-DD HH:MM'")
    ap.add_argument("--end", default=None, help="last time to keep, 'YYYY-MM-DD HH:MM'")
    ap.add_argument("--out", default="wrf_subset.nc", help="output NetCDF")
    args = ap.parse_args()

    ds = open_wrf(args.pattern)
    times = get_times(ds)
    lat, lon = get_latlon(ds)

    sel: dict[str, slice] = {}
    if any(v is not None for v in (args.lat_min, args.lat_max,
                                   args.lon_min, args.lon_max)):
        inside = np.ones(lat.shape, dtype=bool)
        if args.lat_min is not None:
            inside &= lat >= args.lat_min
        if args.lat_max is not None:
            inside &= lat <= args.lat_max
        if args.lon_min is not None:
            inside &= lon >= args.lon_min
        if args.lon_max is not None:
            inside &= lon <= args.lon_max
        if not inside.any():
            raise SystemExit("No grid cells fall inside the requested box")
        rows = np.where(inside.any(axis=1))[0]
        cols = np.where(inside.any(axis=0))[0]
        sel["south_north"] = slice(int(rows.min()), int(rows.max()) + 1)
        sel["west_east"] = slice(int(cols.min()), int(cols.max()) + 1)
        # staggered grids, when present, follow their own extents
        for dim, parent in (("south_north_stag", "south_north"),
                            ("west_east_stag", "west_east")):
            if dim in ds.dims and parent in sel:
                s = sel[parent]
                sel[dim] = slice(s.start, min(s.stop + 1, ds.sizes[dim]))

    if args.start or args.end:
        mask = np.ones(len(times), dtype=bool)
        if args.start:
            mask &= times >= pd.Timestamp(args.start)
        if args.end:
            mask &= times <= pd.Timestamp(args.end)
        if not mask.any():
            raise SystemExit("No timesteps fall inside the requested time range")
        idx = np.where(mask)[0]
        sel["Time"] = slice(int(idx.min()), int(idx.max()) + 1)

    sub = ds.isel(sel)
    sub.to_netcdf(args.out)
    nlat, nlon = get_latlon(sub)
    print(f"Wrote {args.out}")
    print(f"  times : {sub.sizes['Time']} steps")
    print(f"  grid  : {nlat.shape[0]} x {nlat.shape[1]} "
          f"(lat {nlat.min():.3f}..{nlat.max():.3f}, "
          f"lon {nlon.min():.3f}..{nlon.max():.3f})")
    ds.close()


if __name__ == "__main__":
    main()
