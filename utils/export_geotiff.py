#!/usr/bin/env python3
"""Export one wrfout variable at one time as a GeoTIFF for QGIS / GIS use.

WRF grids are curvilinear, so the field is first interpolated onto a
regular lat/lon grid (WGS84, EPSG:4326). The GeoTIFF is written by a small
built-in writer -- neither rasterio nor GDAL is required.

Usage:
    python export_geotiff.py 'wrfout_d01_*' --var RAIN_INTERVAL --out rain.tif
    python export_geotiff.py 'wrfout_d01_*' --var T2 --time-index 6 \
        --resolution 0.05 --method linear --out t2.tif
"""

from __future__ import annotations

import argparse
import struct

import numpy as np

from common import (decumulate, get_latlon, get_times, open_wrf, resolve_var,
                    select_time_index, total_rain)

NODATA = -9999.0


# --------------------------------------------------------------------------- #
# Minimal classic-TIFF / GeoTIFF writer (float32, single strip, north-up)
# --------------------------------------------------------------------------- #
def write_geotiff(path: str, data: np.ndarray, lon_min: float, lat_max: float,
                  res_x: float, res_y: float) -> None:
    data = np.ascontiguousarray(data, dtype="<f4")
    h, w = data.shape
    pixel_bytes = data.tobytes()

    # tag -> (type, values); type: 3=SHORT, 4=LONG, 5=RATIONAL, 12=DOUBLE, 2=ASCII
    geokeys = (1, 1, 0, 3, 1024, 0, 1, 2, 1025, 0, 1, 1, 2048, 0, 1, 4326)
    tags: dict[int, tuple[int, tuple]] = {
        256: (4, (w,)),                    # ImageWidth
        257: (4, (h,)),                    # ImageLength
        258: (3, (32,)),                   # BitsPerSample
        259: (3, (1,)),                    # Compression = none
        262: (3, (1,)),                    # Photometric = BlackIsZero
        273: (4, (0,)),                    # StripOffsets (patched below)
        277: (3, (1,)),                    # SamplesPerPixel
        278: (4, (h,)),                    # RowsPerStrip
        279: (4, (len(pixel_bytes),)),     # StripByteCounts
        284: (3, (1,)),                    # PlanarConfiguration
        339: (3, (3,)),                    # SampleFormat = IEEE float
        33550: (12, (res_x, res_y, 0.0)),  # ModelPixelScale
        33922: (12, (0.0, 0.0, 0.0, lon_min, lat_max, 0.0)),  # ModelTiepoint
        34735: (3, geokeys),               # GeoKeyDirectory
        34737: (2, tuple(b"WGS 84\x00")),  # GeoAsciiParams
        42113: (2, tuple(b"-9999\x00")),   # GDAL_NODATA
    }
    type_size = {2: 1, 3: 2, 4: 4, 5: 8, 12: 8}
    fmt_char = {2: "B", 3: "H", 4: "I", 12: "d"}

    def pack_values(ttype: int, values: tuple) -> bytes:
        if ttype == 2:
            return bytes(values)
        if ttype == 5:
            out = b""
            for num, den in values:
                out += struct.pack("<II", num, den)
            return out
        return struct.pack("<" + fmt_char[ttype] * len(values), *values)

    n = len(tags)
    ifd_size = 2 + n * 12 + 4
    ext_start = 8 + ifd_size

    # first pass: assign offsets for values that do not fit in 4 bytes
    offsets: dict[int, int] = {}
    cursor = ext_start
    for tag in sorted(tags):
        ttype, values = tags[tag]
        raw = pack_values(ttype, values)
        if len(raw) > 4:
            offsets[tag] = cursor
            cursor += len(raw) + (len(raw) % 2)
    strip_offset = cursor
    tags[273] = (4, (strip_offset,))

    out = bytearray()
    out += struct.pack("<HHI", 0x4949, 42, 8)  # little endian, IFD at 8
    out += struct.pack("<H", n)
    for tag in sorted(tags):
        ttype, values = tags[tag]
        raw = pack_values(ttype, values)
        count = len(values)
        out += struct.pack("<HHI", tag, ttype, count)
        if len(raw) <= 4:
            out += raw.ljust(4, b"\x00")
        else:
            out += struct.pack("<I", offsets[tag])
    out += struct.pack("<I", 0)  # no next IFD
    for tag in sorted(tags):
        ttype, values = tags[tag]
        raw = pack_values(ttype, values)
        if len(raw) > 4:
            assert len(out) == offsets[tag], (tag, len(out), offsets[tag])
            out += raw
            if len(raw) % 2:
                out += b"\x00"
    assert len(out) == strip_offset
    out += pixel_bytes
    with open(path, "wb") as fh:
        fh.write(out)


# --------------------------------------------------------------------------- #
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pattern", help="glob pattern for wrfout files, e.g. 'wrfout_d01_*'")
    ap.add_argument("--var", default="RAIN_INTERVAL",
                    help="variable or shortcut (default RAIN_INTERVAL)")
    ap.add_argument("--time-index", type=int, default=None)
    ap.add_argument("--time", default=None, help="timestamp 'YYYY-MM-DD HH:MM'")
    ap.add_argument("--level", type=int, default=0,
                    help="bottom_top level index for 3-D variables (default 0)")
    ap.add_argument("--resolution", type=float, default=None,
                    help="output grid spacing in degrees (default: native spacing)")
    ap.add_argument("--method", choices=("nearest", "linear"), default="nearest",
                    help="interpolation onto the regular grid (default nearest)")
    ap.add_argument("--out", default="wrf_export.tif", help="output GeoTIFF")
    args = ap.parse_args()

    ds = open_wrf(args.pattern)
    times = get_times(ds)
    idx = select_time_index(ds, args.time_index, args.time)
    lat, lon = get_latlon(ds)

    key = args.var.upper()
    if key == "RAIN_INTERVAL":
        field = decumulate(total_rain(ds)).isel(Time=idx)
    else:
        var = resolve_var(ds, args.var)
        field = var.isel(Time=idx)
        if "bottom_top" in field.dims:
            field = field.isel(bottom_top=args.level)
    values = np.asarray(field.values, dtype=float)
    if values.ndim != 2:
        raise SystemExit(f"Variable {args.var} has shape {values.shape}; "
                         "expected a 2-D field")

    res = args.resolution
    if res is None:
        res = float(np.median(np.abs(np.diff(lon[lon.shape[0] // 2, :]))))
    lon_min, lon_max = float(lon.min()), float(lon.max())
    lat_min, lat_max = float(lat.min()), float(lat.max())
    grid_lon = np.arange(lon_min, lon_max + 0.5 * res, res)
    grid_lat = np.arange(lat_max, lat_min - 0.5 * res, -res)  # north-up

    from scipy.interpolate import LinearNDInterpolator, NearestNDInterpolator

    points = np.column_stack([lon.ravel(), lat.ravel()])
    vals = values.ravel()
    finite = np.isfinite(vals)
    if args.method == "linear":
        interp = LinearNDInterpolator(points[finite], vals[finite])
    else:
        interp = NearestNDInterpolator(points[finite], vals[finite])
    glon, glat = np.meshgrid(grid_lon, grid_lat)
    grid = np.asarray(interp(glon, glat), dtype=float)
    grid[~np.isfinite(grid)] = NODATA

    write_geotiff(args.out, grid, float(grid_lon[0]), float(grid_lat[0]),
                  float(grid_lon[1] - grid_lon[0]),
                  float(abs(grid_lat[1] - grid_lat[0])))
    print(f"Wrote {args.out}")
    print(f"  variable: {args.var} at {times[idx]} (time index {idx})")
    print(f"  grid    : {grid.shape[1]} x {grid.shape[0]} at {res:.4f} deg, "
          f"EPSG:4326, nodata {NODATA}")
    ds.close()


if __name__ == "__main__":
    main()
