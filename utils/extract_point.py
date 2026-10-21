#!/usr/bin/env python3
"""Extract a time series at one lat/lon point from wrfout files, as CSV.

The nearest grid cell is used; its actual lat/lon and its distance from
the requested point are printed on stdout.

Columns: time, rain_interval_mm, rain_accum_mm (when RAINC/RAINNC exist),
then each requested variable, plus wind_speed / wind_dir when both U10 and
V10 are available. Wind direction is meteorological (degrees FROM which
the wind blows, 0 = north).

Usage:
    python extract_point.py 'wrfout_d01_*' --lat -6.2 --lon 106.8
    python extract_point.py 'wrfout_d01_*' --lat 1.5 --lon 110.4 \
        --vars T2 PSFC Q2 --out jakarta.csv
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from common import (decumulate, get_latlon, get_times, nearest_point,
                    open_wrf, total_rain, wind_speed_dir)

DEFAULT_VARS = ("T2", "U10", "V10", "PSFC", "Q2")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pattern", help="glob pattern for wrfout files, e.g. 'wrfout_d01_*'")
    ap.add_argument("--lat", type=float, required=True, help="target latitude")
    ap.add_argument("--lon", type=float, required=True, help="target longitude")
    ap.add_argument("--vars", nargs="+", default=list(DEFAULT_VARS),
                    help=f"2-D variables to include (default: {' '.join(DEFAULT_VARS)})")
    ap.add_argument("--out", default="point_series.csv", help="output CSV")
    ap.add_argument("--include-snow", action="store_true",
                    help="include SNOWNC/GRAUPELNC in the rain totals")
    args = ap.parse_args()

    ds = open_wrf(args.pattern)
    times = get_times(ds)
    lat, lon = get_latlon(ds)
    j, i, dist = nearest_point(lat, lon, args.lat, args.lon)
    print(f"Target      : {args.lat:.4f}, {args.lon:.4f}")
    print(f"Nearest cell: {lat[j, i]:.4f}, {lon[j, i]:.4f} "
          f"(j={j}, i={i}, {dist:.2f} km away)")

    data: dict[str, object] = {"time": times}
    if "RAINC" in ds and "RAINNC" in ds:
        accum = total_rain(ds, include_snow=args.include_snow)
        data["rain_interval_mm"] = decumulate(accum).values[:, j, i]
        data["rain_accum_mm"] = accum.values[:, j, i]

    present = []
    for name in args.vars:
        if name in ds and ds[name].dims[-2:] == ("south_north", "west_east"):
            data[name] = ds[name].values[:, j, i]
            present.append(name)
        else:
            print(f"warning: variable {name} not available as a 2-D field; skipped")

    if "U10" in present and "V10" in present:
        ws, wd = wind_speed_dir(data["U10"], data["V10"])
        data["wind_speed"] = ws
        data["wind_dir"] = wd

    df = pd.DataFrame(data)
    df.to_csv(args.out, index=False, date_format="%Y-%m-%dT%H:%M:%S")
    print(f"Wrote {args.out} ({len(df)} rows, columns: {', '.join(df.columns)})")
    ds.close()


if __name__ == "__main__":
    main()
