#!/usr/bin/env python3
"""Extract precipitation from wrfout files into a clean NetCDF.

Total rain is RAINC + RAINNC (mm). WRF stores these accumulated since the
start of the run; this util de-cumulates them into interval rain, optionally
resampled to a fixed interval (e.g. hourly or daily sums).

Usage:
    python extract_rain.py 'wrfout_d01_*'                  # native output steps
    python extract_rain.py 'wrfout_d01_*' --interval 1h    # hourly sums
    python extract_rain.py 'wrfout_d01_*' --interval 24h --out daily_rain.nc
    python extract_rain.py 'wrfout_d01_*' --include-snow

Output NetCDF contains:
    rain_interval   interval precipitation (mm) on the native WRF grid,
                    with XLAT / XLONG coordinates attached
    rain_accum      accumulated total at the end of each interval (mm)
"""

from __future__ import annotations

import argparse

import numpy as np
import xarray as xr

from common import SN, TIME_DIM, WE, decumulate, get_latlon, open_wrf, total_rain


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pattern", help="glob pattern for wrfout files, e.g. 'wrfout_d01_*'")
    ap.add_argument("--out", default="rain.nc", help="output NetCDF (default rain.nc)")
    ap.add_argument("--interval", default=None,
                    help="resample interval for sums, e.g. 1h, 3h, 6h, 24h "
                         "(default: native output steps)")
    ap.add_argument("--include-snow", action="store_true",
                    help="add SNOWNC and GRAUPELNC when present")
    args = ap.parse_args()

    ds = open_wrf(args.pattern)
    accum = total_rain(ds, include_snow=args.include_snow)
    interval = decumulate(accum)

    if args.interval:
        interval = interval.resample({TIME_DIM: args.interval}).sum()
        accum_out = accum.resample({TIME_DIM: args.interval}).max()
        label = f"resampled to {args.interval}"
    else:
        accum_out = accum
        label = "native output steps"

    lat, lon = get_latlon(ds)
    out = xr.Dataset(
        {
            "rain_interval": interval,
            "rain_accum": accum_out,
        },
        coords={
            "XLAT": ((SN, WE), lat),
            "XLONG": ((SN, WE), lon),
        },
        attrs={
            "description": f"WRF precipitation, {label}",
            "source_pattern": args.pattern,
            "units_note": "all precipitation variables in mm",
        },
    )
    out["rain_interval"].attrs.update(units="mm")
    out["rain_accum"].attrs.update(units="mm")
    out.to_netcdf(args.out)

    vals = np.asarray(out["rain_interval"].values)
    print(f"Wrote {args.out}")
    print(f"  intervals : {vals.shape[0]} ({label})")
    print(f"  grid      : {vals.shape[1]} x {vals.shape[2]}")
    print(f"  max interval rain : {np.nanmax(vals):.2f} mm")
    print(f"  final accumulated : {float(out['rain_accum'].values[-1].max()):.2f} mm")
    ds.close()


if __name__ == "__main__":
    main()
