# WRF post-processing utils

A small toolbox for working with `wrfout` files: inspect a run, extract
rain, plot maps, pull point time series, animate, subset, export to GIS,
and preview your domains before you run.

Design rules:

- **No hardcoded paths, dates, grid sizes or timesteps.** Everything comes
  from command-line arguments or from the files themselves, so the same
  command works on any run, any domain, any date.
- **Real coordinates.** Maps always use the file's own `XLAT`/`XLONG`
  (WRF grids are curvilinear) — never a reconstructed evenly spaced grid.
- **Rain done right.** `RAINC + RAINNC` is accumulated since run start;
  the utils de-cumulate it into interval rain, with restart resets handled.
- Every script explains itself with `--help`.

## Install

```bash
pip install -r requirements.txt
```

Core needs only numpy / pandas / xarray / netCDF4 / matplotlib / scipy /
Pillow. **cartopy is optional** — install it for coastlines and borders;
without it, maps fall back to plain lat/lon with a printed note.
No wrf-python, rasterio or GDAL is required anywhere.

## The utils

### 1. `inspect_wrf.py` — see a run at a glance

```bash
python inspect_wrf.py 'wrfout_d01_*'
python inspect_wrf.py 'wrfout_d02_*' --full   # list every variable
```

Prints file list, time range and output interval, grid size, lat/lon
ranges, key global attributes (DX, CEN_LAT, MAP_PROJ, ...) and variables.

### 2. `extract_rain.py` — precipitation to a clean NetCDF

```bash
python extract_rain.py 'wrfout_d01_*'                    # native steps
python extract_rain.py 'wrfout_d01_*' --interval 1h      # hourly sums
python extract_rain.py 'wrfout_d01_*' --interval 24h --out daily.nc
python extract_rain.py 'wrfout_d01_*' --include-snow     # + SNOWNC/GRAUPELNC
```

Output contains `rain_interval` (mm per interval) and `rain_accum` (mm),
with the real `XLAT`/`XLONG` attached.

### 3. `plot_map.py` — map any variable to PNG

```bash
python plot_map.py 'wrfout_d01_*'                          # interval rain, last step
python plot_map.py 'wrfout_d01_*' --var T2 --time '2024-11-17 05:00'
python plot_map.py 'wrfout_d01_*' --var RAIN --time-index 10 --vmax 100
python plot_map.py 'wrfout_d01_*' --var U --level 5        # 3-D var, level index
```

Shortcuts: `RAIN` (accumulated), `RAIN_INTERVAL` (rain in the step ending
at the chosen time), `WS10` (10 m wind speed). Anything else is the raw
variable of that name.

### 4. `extract_point.py` — time series at a lat/lon, as CSV

```bash
python extract_point.py 'wrfout_d01_*' --lat -6.2 --lon 106.8
python extract_point.py 'wrfout_d01_*' --lat 1.5 --lon 110.4 --vars T2 PSFC Q2
```

Uses the nearest grid cell (its true lat/lon and distance are printed).
Columns: time, rain interval + accumulated, the requested variables, and
wind speed / direction when U10 and V10 are present. Direction is
meteorological — degrees *from* which the wind blows.

### 5. `animate.py` — GIF / MP4 over time

```bash
python animate.py 'wrfout_d01_*'                            # interval rain GIF
python animate.py 'wrfout_d01_*' --var T2 --fps 4 --out t2.gif
python animate.py 'wrfout_d01_*' --var RAIN --accumulated --vmax 150
```

Colour limits are fixed across frames (default: 99th percentile) so the
frames stay comparable. MP4 output needs ffmpeg; GIF works anywhere.

### 6. `subset_wrf.py` — cut a smaller NetCDF

```bash
python subset_wrf.py 'wrfout_d01_*' --lat-min -7 --lat-max -5 \
    --lon-min 105 --lon-max 108 --out jakarta_box.nc
python subset_wrf.py 'wrfout_d01_*' --start '2024-11-17 03:00' \
    --end '2024-11-17 12:00' --out morning.nc
```

The box is applied on the file's own `XLAT`/`XLONG`; the smallest index
ranges covering the box are kept.

### 7. `export_geotiff.py` — a field for QGIS

```bash
python export_geotiff.py 'wrfout_d01_*' --var RAIN_INTERVAL --out rain.tif
python export_geotiff.py 'wrfout_d01_*' --var T2 --time-index 6 \
    --resolution 0.05 --method linear --out t2.tif
```

Interpolates the curvilinear field onto a regular WGS84 (EPSG:4326) grid
and writes a float32 GeoTIFF with a built-in writer — no GDAL needed.
Nodata is -9999.

### 8. `plot_domains.py` — preview domains from namelist.wps

```bash
python plot_domains.py namelist.wps
python plot_domains.py namelist.wps --out domains.png
```

Draws every nest and prints each domain's grid, dx, size in km, centre and
corners — catch a misplaced or escaping child *before* burning a run.
Supports `lambert`, `mercator` and `lat-lon`. Positions are preview-grade
(spherical earth, R = 6370 km as in WRF): right for checking placement and
nesting, not a substitute for `geogrid.exe`.

## Shared code

`common.py` holds what every util needs: opening and time-sorting wrfout
sets, `XLAT`/`XLONG` access, nearest-cell lookup, rain total +
de-cumulation (restart-safe), wind speed/direction, and cartopy-aware map
plotting.

## Tests

```bash
python tests/test_utils.py
```

This generates synthetic wrfout files whose rain, temperature, winds and
coordinates are analytic ("planted truth"), runs all 8 utils as real CLI
commands, and checks the outputs against the planted values — de-cumulated
rain recovers the planted hourly rates exactly, point extraction returns
the planted cell values, the GeoTIFF carries the planted value at the
planted coordinates, domain centres land on the namelist reference point,
and the southern-hemisphere Lambert projection round-trips. 35 checks.

## Legacy scripts

`get_rain.py` and `plot_rain.py` are the original one-case scripts
(Nov 2024 case, hardcoded paths/dates/grid), kept for history.
Use `extract_rain.py` and `plot_map.py` instead — they do the same job
for any run.
