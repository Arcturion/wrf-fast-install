#!/usr/bin/env python3
"""Generate small synthetic wrfout files with PLANTED, known values.

The utils are tested against these files: because the rain field, the
temperature field, the winds and the grid coordinates are all analytic,
every util's output can be checked exactly instead of eyeballed.

Grid   : 20 x 24 (south_north x west_east), curvilinear XLAT/XLONG
Times  : 6 hourly steps from 2024-11-17 00:00 UTC, split over two files
Rain   : hourly rate[t,j,i] = (0.5 + 0.1 t)(1 + i/24) + 0.02 j   [mm]
         RAINC = 0.7 * cumsum(rate), RAINNC = 0.3 * cumsum(rate)
T2     : 298 + 0.5 t - 0.05 j + 0.01 i                            [K]
U10/V10: constant 3 / 4  ->  wind speed 5 m/s, direction 216.87 deg
T (3-D): 280 + 2*level - 0.1 j                                    [K]

Outputs (in the target directory):
    wrfout_d01_2024-11-17_00:00:00   (steps 0-2)
    wrfout_d01_2024-11-17_03:00:00   (steps 3-5)
    planted.npz                      (the truth, for the tests)
"""

from __future__ import annotations

import os
import sys

import netCDF4 as nc
import numpy as np

SN, WE, BT, NT = 20, 24, 4, 6
START = np.datetime64("2024-11-17T00:00:00")


def planted_fields():
    jj, ii = np.meshgrid(np.arange(SN), np.arange(WE), indexing="ij")
    lat = -2.0 + jj * 0.1 + 0.02 * np.sin(ii * 0.5)
    lon = 110.0 + ii * 0.1 + 0.02 * np.cos(jj * 0.5)
    rate = np.stack([(0.5 + 0.1 * t) * (1.0 + ii / 24.0) + 0.02 * jj
                     for t in range(NT)]).astype(np.float64)
    accum = np.cumsum(rate, axis=0)
    t2 = np.stack([298.0 + 0.5 * t - 0.05 * jj + 0.01 * ii
                   for t in range(NT)])
    return lat, lon, rate, accum, t2


def write_file(path, steps, lat, lon, accum, t2):
    n = len(steps)
    ds = nc.Dataset(path, "w", format="NETCDF4_CLASSIC")
    ds.createDimension("Time", None)
    ds.createDimension("DateStrLen", 19)
    ds.createDimension("south_north", SN)
    ds.createDimension("west_east", WE)
    ds.createDimension("bottom_top", BT)

    times_var = ds.createVariable("Times", "S1", ("Time", "DateStrLen"))
    xtime = ds.createVariable("XTIME", "f8", ("Time",))
    xtime.units = "minutes since 2024-11-17 00:00:00"
    xtime.calendar = "standard"

    def var3(name, units, desc):
        v = ds.createVariable(name, "f4", ("Time", "south_north", "west_east"))
        v.units = units
        v.description = desc
        return v

    xlat = ds.createVariable("XLAT", "f4", ("Time", "south_north", "west_east"))
    xlat.units = "degree_north"
    xlon = ds.createVariable("XLONG", "f4", ("Time", "south_north", "west_east"))
    xlon.units = "degree_east"
    rainc = var3("RAINC", "mm", "accumulated total grid scale precipitation")
    rainnc = var3("RAINNC", "mm", "accumulated total cumulus precipitation")
    snownc = var3("SNOWNC", "mm", "accumulated total grid scale snow")
    graupel = var3("GRAUPELNC", "mm", "accumulated total grid scale graupel")
    t2v = var3("T2", "K", "temperature at 2 m")
    u10 = var3("U10", "m s-1", "u wind at 10 m")
    v10 = var3("V10", "m s-1", "v wind at 10 m")
    psfc = var3("PSFC", "Pa", "surface pressure")
    q2 = var3("Q2", "kg kg-1", "vapour mixing ratio at 2 m")
    hgt = var3("HGT", "m", "terrain height")
    tvar = ds.createVariable("T", "f4",
                             ("Time", "bottom_top", "south_north", "west_east"))
    tvar.units = "K"

    jj, ii = np.meshgrid(np.arange(SN), np.arange(WE), indexing="ij")
    date_strs = []
    for k, t in enumerate(steps):
        stamp = str(START + np.timedelta64(int(t), "h"))
        date_str = stamp.replace("T", "_") + ".0000"
        date_str = date_str[:19]
        date_strs.append(date_str)
        times_var[k] = nc.stringtochar(np.array([date_str], dtype="S19"))
        xtime[k] = t * 60.0
        xlat[k] = lat
        xlon[k] = lon
        rainc[k] = 0.7 * accum[t]
        rainnc[k] = 0.3 * accum[t]
        snownc[k] = 0.0
        graupel[k] = 0.0
        t2v[k] = t2[t]
        u10[k] = 3.0
        v10[k] = 4.0
        psfc[k] = 100000.0 - 10.0 * jj - 5.0 * ii
        q2[k] = 0.012
        hgt[k] = 100.0 + 0.1 * jj * ii
        for lev in range(BT):
            tvar[k, lev] = 280.0 + 2.0 * lev - 0.1 * jj

    ds.TITLE = "Synthetic wrfout for utils testing (planted truth)"
    ds.START_DATE = date_strs[0]
    ds.DX = 11000.0
    ds.DY = 11000.0
    ds.CEN_LAT = -1.05
    ds.CEN_LON = 111.15
    ds.MAP_PROJ = 1
    ds.TRUELAT1 = -5.0
    ds.TRUELAT2 = -15.0
    ds.STAND_LON = 111.0
    ds.setncattr("WEST-EAST_GRID_DIMENSION", WE + 1)
    ds.setncattr("SOUTH-NORTH_GRID_DIMENSION", SN + 1)
    ds.setncattr("BOTTOM-TOP_GRID_DIMENSION", BT + 1)
    ds.close()


def main(outdir: str) -> None:
    os.makedirs(outdir, exist_ok=True)
    lat, lon, rate, accum, t2 = planted_fields()
    write_file(os.path.join(outdir, "wrfout_d01_2024-11-17_00:00:00"),
               [0, 1, 2], lat, lon, accum, t2)
    write_file(os.path.join(outdir, "wrfout_d01_2024-11-17_03:00:00"),
               [3, 4, 5], lat, lon, accum, t2)
    np.savez(os.path.join(outdir, "planted.npz"),
             lat=lat, lon=lon, rate=rate, accum=accum, t2=t2)
    print(f"Synthetic wrfout written to {outdir}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "synthetic")
