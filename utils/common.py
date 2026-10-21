"""Shared helpers for the WRF post-processing utilities.

Design rules for every util in this folder:
  * No hardcoded paths, dates, grid sizes or timesteps -- everything comes
    from CLI arguments or from the wrfout files themselves.
  * Coordinates always come from the file's own XLAT / XLONG (WRF grids are
    curvilinear); never reconstruct an evenly spaced lat/lon grid.
  * Only hard dependencies are numpy / pandas / xarray / netCDF4 /
    matplotlib. cartopy is used when installed and is optional.
"""

from __future__ import annotations

import glob as _glob
import sys

import numpy as np
import pandas as pd
import xarray as xr

TIME_DIM = "Time"
SN = "south_north"
WE = "west_east"


# --------------------------------------------------------------------------- #
# Opening wrfout files
# --------------------------------------------------------------------------- #
def find_files(pattern: str) -> list[str]:
    """Expand a glob pattern into a non-empty, sorted file list."""
    files = sorted(_glob.glob(pattern))
    if not files:
        raise SystemExit(f"No files match pattern: {pattern!r}")
    return files


def get_times(ds: xr.Dataset) -> pd.DatetimeIndex:
    """Return the dataset times as a DatetimeIndex.

    Primary source is XTIME (a CF time coordinate in real wrfout). Falls back
    to decoding the character `Times` variable (DateStrLen=19 strings).
    """
    if "XTIME" in ds:
        vals = np.asarray(ds["XTIME"].values).ravel()
        return pd.DatetimeIndex(pd.to_datetime(vals))
    if "Times" in ds:
        raw = ds["Times"].values  # (Time, DateStrLen) of bytes / str
        strs = []
        for row in raw:
            if row.dtype.kind == "S":
                strs.append(b"".join(row).decode("ascii", "ignore").strip())
            else:
                strs.append("".join(str(c) for c in row).strip())
        return pd.DatetimeIndex(
            pd.to_datetime(strs, format="%Y-%m-%d_%H:%M:%S")
        )
    raise SystemExit("Dataset has neither XTIME nor Times -- not a wrfout file?")


def open_wrf(pattern: str) -> xr.Dataset:
    """Open one or more wrfout files and concatenate them in time order.

    Each file is opened separately, the list is sorted by its first time,
    and the pieces are concatenated along Time. The Time dimension gets a
    proper datetime coordinate so .sel(Time=...) and .resample() work.
    """
    files = find_files(pattern)
    pieces = []
    for f in files:
        ds = xr.open_dataset(f)
        pieces.append((get_times(ds)[0], ds))
    pieces.sort(key=lambda p: p[0])
    datasets = [p[1] for p in pieces]
    if len(datasets) == 1:
        ds = datasets[0]
    else:
        ds = xr.concat(datasets, dim=TIME_DIM)
    times = get_times(ds)
    ds = ds.assign_coords(Time=("Time", times.values))
    return ds


# --------------------------------------------------------------------------- #
# Grid / coordinates
# --------------------------------------------------------------------------- #
def get_latlon(ds: xr.Dataset) -> tuple[np.ndarray, np.ndarray]:
    """Return (lat, lon) as 2-D arrays [south_north, west_east]."""
    lat = ds["XLAT"]
    lon = ds["XLONG"]
    if TIME_DIM in lat.dims:
        lat = lat.isel(Time=0)
    if TIME_DIM in lon.dims:
        lon = lon.isel(Time=0)
    return np.asarray(lat.values, dtype=float), np.asarray(lon.values, dtype=float)


def nearest_point(
    lat: np.ndarray, lon: np.ndarray, target_lat: float, target_lon: float
) -> tuple[int, int, float]:
    """Indices (j, i) of the grid cell nearest to (target_lat, target_lon).

    Also returns the great-circle distance in km (haversine).
    """
    d2 = (lat - target_lat) ** 2 + (lon - target_lon) ** 2
    j, i = np.unravel_index(int(np.argmin(d2)), d2.shape)
    r = 6371.0
    p1, p2 = np.radians(lat[j, i]), np.radians(target_lat)
    dp = p2 - p1
    dl = np.radians(lon[j, i] - target_lon)
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    dist = 2 * r * np.arcsin(np.sqrt(a))
    return int(j), int(i), float(dist)


# --------------------------------------------------------------------------- #
# Rain
# --------------------------------------------------------------------------- #
RAIN_COMPONENTS = ("RAINC", "RAINNC")


def total_rain(ds: xr.Dataset, include_snow: bool = False) -> xr.DataArray:
    """Accumulated total precipitation (mm) = RAINC + RAINNC.

    With include_snow=True, SNOWNC and GRAUPELNC are added when present
    (their water equivalent is already in mm in WRF output).
    """
    missing = [v for v in RAIN_COMPONENTS if v not in ds]
    if missing:
        raise SystemExit(f"Missing rain variables in dataset: {missing}")
    total = ds["RAINC"] + ds["RAINNC"]
    if include_snow:
        for v in ("SNOWNC", "GRAUPELNC"):
            if v in ds:
                total = total + ds[v]
    total.attrs.update(units="mm", long_name="accumulated total precipitation")
    return total


def decumulate(total: xr.DataArray) -> xr.DataArray:
    """Convert accumulated rain into per-output-step interval rain (mm).

    Interval k is total[k] - total[k-1]; interval 0 is total[0] itself
    (accumulation since model start). Negative jumps happen when a run was
    restarted and the accumulation reset to zero -- in that case the value
    after the reset is used as the interval.
    """
    vals = np.asarray(total.values, dtype=float)
    out = np.empty_like(vals)
    out[0] = vals[0]
    diff = np.diff(vals, axis=0)
    prev = vals[:-1]
    out[1:] = np.where(diff < 0, vals[1:], diff)
    _ = prev  # (kept for readability of the reset rule above)
    da = xr.DataArray(out, dims=total.dims, coords=total.coords, attrs=dict(total.attrs))
    da.attrs.update(long_name="interval precipitation (per output step)")
    return da


# --------------------------------------------------------------------------- #
# Generic variable access
# --------------------------------------------------------------------------- #
def resolve_var(ds: xr.Dataset, name: str) -> xr.DataArray:
    """Resolve a variable name, including a few derived conveniences.

    RAIN / RAIN_TOTAL -> accumulated total rain
    WS10              -> 10 m wind speed from U10/V10
    anything else     -> the raw variable of that name
    """
    key = name.upper()
    if key in ("RAIN", "RAIN_TOTAL", "PRECIP"):
        return total_rain(ds)
    if key == "WS10":
        if "U10" not in ds or "V10" not in ds:
            raise SystemExit("WS10 needs U10 and V10 in the dataset")
        ws = np.sqrt(ds["U10"] ** 2 + ds["V10"] ** 2)
        ws.attrs.update(units="m s-1", long_name="10 m wind speed")
        return ws
    if name not in ds:
        avail = ", ".join(sorted(ds.data_vars))
        raise SystemExit(f"Variable {name!r} not in dataset. Available: {avail}")
    return ds[name]


def wind_speed_dir(u: np.ndarray | float, v: np.ndarray | float):
    """Meteorological wind speed and direction (deg, FROM which it blows)."""
    ws = np.sqrt(np.asarray(u, dtype=float) ** 2 + np.asarray(v, dtype=float) ** 2)
    wd = (270.0 - np.degrees(np.arctan2(v, u))) % 360.0
    return ws, wd


def select_time_index(ds: xr.Dataset, time_index: int | None,
                      time_str: str | None) -> int:
    """Resolve --time / --time-index arguments into a positional index."""
    times = get_times(ds)
    n = len(times)
    if time_str:
        target = pd.Timestamp(time_str)
        pos = int(np.argmin(np.abs(times - target)))
        if times[pos] != target:
            print(f"note: no exact step at {target}; using nearest {times[pos]}",
                  file=sys.stderr)
        return pos
    idx = -1 if time_index is None else time_index
    if idx < 0:
        idx += n
    if not 0 <= idx < n:
        raise SystemExit(f"time index {time_index} out of range (0..{n - 1})")
    return idx


# --------------------------------------------------------------------------- #
# Plotting (cartopy optional)
# --------------------------------------------------------------------------- #
def make_map_ax(figsize=(9, 8)):
    """Return (fig, ax, using_cartopy). Falls back to plain lat/lon axes."""
    import matplotlib.pyplot as plt

    try:
        import cartopy.crs as ccrs
        import cartopy.feature as cfeature

        fig = plt.figure(figsize=figsize)
        ax = fig.add_subplot(1, 1, 1, projection=ccrs.PlateCarree())
        ax.coastlines(resolution="50m", linewidth=0.6)
        ax.add_feature(cfeature.BORDERS, linewidth=0.4)
        gl = ax.gridlines(draw_labels=True, linewidth=0.3, alpha=0.6)
        gl.top_labels = False
        gl.right_labels = False
        return fig, ax, True
    except Exception:
        fig, ax = plt.subplots(figsize=figsize)
        ax.set_xlabel("Longitude")
        ax.set_ylabel("Latitude")
        ax.grid(True, linewidth=0.3, alpha=0.6)
        return fig, ax, False


def plot_field(ax, lon, lat, field, using_cartopy: bool, **kwargs):
    """pcolormesh a 2-D field on the axis, cartopy-aware.

    shading='nearest' is deliberate: WRF XLAT/XLONG are curvilinear and are
    not monotonic along rows on projected grids, so cell-edge inference
    (shading='auto') warns and can misplace edges. 'nearest' plots the
    values at their true cell centres.
    """
    if using_cartopy:
        import cartopy.crs as ccrs

        return ax.pcolormesh(lon, lat, field, transform=ccrs.PlateCarree(),
                             shading="nearest", **kwargs)
    return ax.pcolormesh(lon, lat, field, shading="nearest", **kwargs)
