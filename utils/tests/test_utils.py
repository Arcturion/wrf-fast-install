#!/usr/bin/env python3
"""Planted-truth tests for the WRF utils.

Generates synthetic wrfout files with known analytic fields, runs every
util as a real CLI subprocess, and checks the outputs against the planted
values. Run:

    python tests/test_utils.py

Exits 0 when all checks pass, 1 otherwise.
"""

from __future__ import annotations

import os
import struct
import subprocess
import sys
import tempfile

import numpy as np
import pandas as pd
import xarray as xr

HERE = os.path.dirname(os.path.abspath(__file__))
UTILS = os.path.dirname(HERE)
sys.path.insert(0, UTILS)
sys.path.insert(0, HERE)

import make_synthetic_wrfout as gen  # noqa: E402

RESULTS = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(ok)))
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}")


def run_cli(script: str, *args: str, cwd: str) -> subprocess.CompletedProcess:
    proc = subprocess.run(
        [sys.executable, os.path.join(UTILS, script), *args],
        cwd=cwd, capture_output=True, text=True)
    if proc.returncode != 0:
        print(f"--- {script} {' '.join(args)} failed ---\n"
              f"{proc.stdout}\n{proc.stderr}")
    return proc


def read_geotiff(path: str):
    """Minimal TIFF reader for the test: returns (array, tags dict)."""
    with open(path, "rb") as fh:
        blob = fh.read()
    assert blob[:2] == b"II" and struct.unpack("<H", blob[2:4])[0] == 42
    ifd_off = struct.unpack("<I", blob[4:8])[0]
    n = struct.unpack("<H", blob[ifd_off:ifd_off + 2])[0]
    type_size = {2: 1, 3: 2, 4: 4, 12: 8}
    fmt = {3: "H", 4: "I", 12: "d"}
    tags = {}
    for k in range(n):
        e = ifd_off + 2 + k * 12
        tag, ttype, count = struct.unpack("<HHI", blob[e:e + 8])
        raw = blob[e + 8:e + 12]
        size = type_size[ttype] * count
        if size > 4:
            off = struct.unpack("<I", raw)[0]
            raw = blob[off:off + size]
        if ttype == 2:
            tags[tag] = raw
        else:
            tags[tag] = struct.unpack("<" + fmt[ttype] * count, raw[:size])
    w, h = tags[256][0], tags[257][0]
    off = tags[273][0]
    arr = np.frombuffer(blob[off:off + w * h * 4], dtype="<f4").reshape(h, w)
    return arr, tags


def main() -> int:
    work = tempfile.mkdtemp(prefix="wrf_utils_test_")
    data = os.path.join(work, "data")
    out = os.path.join(work, "out")
    os.makedirs(out)
    gen.main(data)
    planted = np.load(os.path.join(data, "planted.npz"))
    lat, lon = planted["lat"], planted["lon"]
    rate, accum, t2 = planted["rate"], planted["accum"], planted["t2"]
    pattern = os.path.join(data, "wrfout_d01_*")

    # ---------------- inspect_wrf ---------------- #
    p = run_cli("inspect_wrf.py", pattern, cwd=out)
    check("inspect runs", p.returncode == 0)
    check("inspect reports 6 times / 2 files",
          "6 steps" in p.stdout and "Files          : 2" in p.stdout,
          p.stdout.splitlines()[0] if p.stdout else "")
    check("inspect lists rain vars", "RAINC" in p.stdout and "RAINNC" in p.stdout)

    # ---------------- extract_rain ---------------- #
    p = run_cli("extract_rain.py", pattern, "--out", "rain.nc", cwd=out)
    check("extract_rain runs", p.returncode == 0)
    r = xr.open_dataset(os.path.join(out, "rain.nc"))
    iv = r["rain_interval"].values
    check("rain_interval shape", iv.shape == rate.shape, str(iv.shape))
    check("rain_interval == planted hourly rate (steps 1..5)",
          np.allclose(iv[1:], rate[1:], atol=1e-5),
          f"max err {np.abs(iv[1:] - rate[1:]).max():.2e}")
    check("rain_interval first step == first planted rate",
          np.allclose(iv[0], rate[0], atol=1e-5))
    check("rain_accum final == planted accumulation",
          np.allclose(r["rain_accum"].values[-1], accum[-1], atol=1e-4))
    check("rain output carries real XLAT/XLONG",
          np.allclose(r["XLAT"].values, lat, atol=1e-6)
          and np.allclose(r["XLONG"].values, lon, atol=1e-6))
    r.close()

    p = run_cli("extract_rain.py", pattern, "--interval", "3h",
                "--out", "rain3h.nc", cwd=out)
    r3 = xr.open_dataset(os.path.join(out, "rain3h.nc"))
    iv3 = r3["rain_interval"].values
    expect3 = np.stack([rate[0:3].sum(axis=0), rate[3:6].sum(axis=0)])
    check("rain 3h resample == planted 3h sums",
          iv3.shape == expect3.shape and np.allclose(iv3, expect3, atol=1e-5),
          str(iv3.shape))
    r3.close()

    # ---------------- extract_point ---------------- #
    j0, i0 = 10, 12
    p = run_cli("extract_point.py", pattern,
                "--lat", str(lat[j0, i0]), "--lon", str(lon[j0, i0]),
                "--out", "point.csv", cwd=out)
    check("extract_point runs", p.returncode == 0)
    df = pd.read_csv(os.path.join(out, "point.csv"))
    check("point CSV rows == 6", len(df) == 6)
    check("point rain_interval == planted rate at cell",
          np.allclose(df["rain_interval_mm"].values, rate[:, j0, i0], atol=1e-4))
    check("point T2 == planted T2 at cell",
          np.allclose(df["T2"].values, t2[:, j0, i0], atol=1e-3))
    check("point wind speed == 5 (planted U=3, V=4)",
          np.allclose(df["wind_speed"].values, 5.0, atol=1e-6))
    check("point wind dir == 216.87 deg (planted)",
          np.allclose(df["wind_dir"].values, 216.8699, atol=0.01),
          f"got {df['wind_dir'].values[0]:.2f}")

    # ---------------- plot_map ---------------- #
    p = run_cli("plot_map.py", pattern, "--time-index", "3",
                "--out", "map.png", cwd=out)
    png = os.path.join(out, "map.png")
    check("plot_map runs and writes PNG",
          p.returncode == 0 and os.path.getsize(png) > 5000)
    p = run_cli("plot_map.py", pattern, "--var", "T", "--level", "2",
                "--time-index", "0", "--out", "map3d.png", cwd=out)
    check("plot_map 3-D var with --level works",
          p.returncode == 0 and os.path.exists(os.path.join(out, "map3d.png")))

    # ---------------- animate ---------------- #
    p = run_cli("animate.py", pattern, "--out", "anim.gif", cwd=out)
    gif = os.path.join(out, "anim.gif")
    ok = p.returncode == 0 and os.path.exists(gif)
    frames = 0
    if ok:
        from PIL import Image
        im = Image.open(gif)
        frames = getattr(im, "n_frames", 0)
    check("animate writes GIF with 6 frames", ok and frames == 6,
          f"frames={frames}")

    # ---------------- subset_wrf ---------------- #
    p = run_cli("subset_wrf.py", pattern,
                "--lat-min", "-1.6", "--lat-max", "-0.9",
                "--start", "2024-11-17 02:00", "--end", "2024-11-17 04:00",
                "--out", "sub.nc", cwd=out)
    sub = xr.open_dataset(os.path.join(out, "sub.nc"))
    check("subset runs", p.returncode == 0)
    check("subset time steps == 3", sub.sizes["Time"] == 3,
          str(sub.sizes["Time"]))
    slat = sub["XLAT"].isel(Time=0).values
    check("subset is smaller than full grid",
          slat.shape[0] < lat.shape[0] and slat.shape[1] <= lat.shape[1],
          str(slat.shape))
    check("subset lat inside requested box (grid tolerance)",
          slat.min() >= -1.7 and slat.max() <= -0.8,
          f"{slat.min():.2f}..{slat.max():.2f}")
    sub.close()

    # ---------------- export_geotiff ---------------- #
    p = run_cli("export_geotiff.py", pattern, "--time-index", "5",
                "--resolution", "0.1", "--out", "rain.tif", cwd=out)
    tif = os.path.join(out, "rain.tif")
    check("export_geotiff runs", p.returncode == 0 and os.path.exists(tif))
    arr, tags = read_geotiff(tif)
    scale = tags[33550]
    tie = tags[33922]
    check("geotiff pixel scale == 0.1 deg",
          abs(scale[0] - 0.1) < 1e-9 and abs(scale[1] - 0.1) < 1e-9,
          str(scale))
    check("geotiff tiepoint == (lon_min, lat_max) of grid",
          abs(tie[3] - lon.min()) < 1e-6 and abs(tie[4] - lat.max()) < 1e-6,
          f"tie={tie[3]:.3f},{tie[4]:.3f} vs {lon.min():.3f},{lat.max():.3f}")
    check("geotiff geokey says EPSG:4326", 4326 in tags[34735],
          str(tags[34735]))
    # nearest-neighbour export: the value at a planted cell centre must be
    # the planted interval rain at that cell (time index 5)
    jj_c = int(round((tie[4] - lat[j0, i0]) / scale[1]))
    ii_c = int(round((lon[j0, i0] - tie[3]) / scale[0]))
    got = float(arr[jj_c, ii_c])
    check("geotiff value at planted cell == planted interval rain",
          abs(got - rate[5, j0, i0]) < 0.35,
          f"got {got:.3f} vs planted {rate[5, j0, i0]:.3f}")

    # ---------------- plot_domains ---------------- #
    namelist = os.path.join(work, "namelist.wps")
    with open(namelist, "w") as fh:
        fh.write(
            "&share\n wrf_core = 'ARW',\n max_dom = 2,\n/\n"
            "&geogrid\n"
            " parent_id         = 1, 1,\n"
            " parent_grid_ratio = 1, 3,\n"
            " i_parent_start    = 1, 20,\n"
            " j_parent_start    = 1, 15,\n"
            " e_we              = 100, 118,\n"
            " e_sn              = 80, 94,\n"
            " geog_data_res     = 'default',\n"
            " dx = 9000,\n dy = 9000,\n"
            " map_proj = 'lambert',\n"
            " ref_lat   = -6.2,\n ref_lon   = 106.8,\n"
            " truelat1  = -10.0,\n truelat2  = -20.0,\n"
            " stand_lon = 106.8,\n"
            "/\n")
    sys.path.insert(0, UTILS)
    import plot_domains as pdm
    cfg = pdm.parse_geogrid(namelist)
    res = pdm.compute_domains(cfg)
    doms = res["domains"]
    check("plot_domains computes 2 domains", len(doms) == 2)
    check("d01 centre == ref point",
          abs(doms[0]["centre"][0] - (-6.2)) < 0.05
          and abs(doms[0]["centre"][1] - 106.8) < 0.05,
          str(doms[0]["centre"]))
    sw, ne = doms[1]["sw"], doms[1]["ne"]
    psw, pne = doms[0]["sw"], doms[0]["ne"]
    check("d02 inside d01 (projected corners ordered)",
          psw[0] < sw[0] < ne[0] < pne[0] and psw[1] < sw[1] < ne[1] < pne[1],
          f"d02 {sw}..{ne} in d01 {psw}..{pne}")
    check("d02 dx == d01 dx / 3",
          doms[1]["dx_label"] == "3 km", doms[1]["dx_label"])
    p = run_cli("plot_domains.py", namelist, "--out", "domains.png", cwd=out)
    check("plot_domains CLI writes PNG",
          p.returncode == 0 and os.path.exists(os.path.join(out, "domains.png")))

    # projection roundtrip (lambert, southern hemisphere)
    proj = pdm.Lambert(-6.2, 106.8, -10.0, -20.0, 106.8)
    x, y = proj.forward(-7.3, 108.1)
    la, lo = proj.inverse(x, y)
    check("lambert forward/inverse roundtrip",
          abs(la - (-7.3)) < 1e-6 and abs(lo - 108.1) < 1e-6,
          f"-> ({la:.6f}, {lo:.6f})")

    # ---------------- legacy scripts still present ---------------- #
    check("legacy get_rain.py / plot_rain.py untouched",
          os.path.exists(os.path.join(UTILS, "get_rain.py"))
          and os.path.exists(os.path.join(UTILS, "plot_rain.py")))

    failed = [n for n, ok in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
    if failed:
        print("FAILED:", ", ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
