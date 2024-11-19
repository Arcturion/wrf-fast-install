import xarray as xr
import numpy as np

data = xr.open_dataset('/content/drive/MyDrive/WRF Out/20241117_00_20241120_00.nc')

# Sort the entire dataset by XTIME (ascending order)
sorted_data = data.sortby(data.XTIME)

# Access sorted variables (RAINC and RAINNC will also be sorted)
sorted_rainc = sorted_data['RAINC']
sorted_rainnc = sorted_data['RAINNC']


# Define the longitude and latitude ranges
lon_min = 110.847
lon_max = 121.153
lat_min = -1.150
lat_max = 9.118


# Create the meshgrid
lons = np.linspace(lon_min, lon_max, 127)
lats = np.linspace(lat_min, lat_max, 127)
lon_grid, lat_grid = np.meshgrid(lons, lats)


new_lon_grid = np.empty((25, 127, 127))
new_lat_grid = np.empty((25, 127, 127))

for i in range(25):
  new_lon_grid[i, :, :] = lon_grid
  new_lat_grid[i, :, :] = lat_grid


# Replace XLONG and XLAT with new_lon_grid and new_lat_grid
sorted_data['XLONG'] = (('Time', 'south_north', 'west_east'), new_lon_grid)
sorted_data['XLAT'] = (('Time', 'south_north', 'west_east'), new_lat_grid)
sorted_data['south_north'] = lats
sorted_data['west_east'] = lons

## TODO : masih cumulative







## PLOT

import xarray as xr
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import cartopy.feature as cfeature
import pandas as pd

ds = sorted_data

# Assuming you want to plot the data for the first timestamp:
time_index = 19  # Adjust this index to select a different timestamp

rainc = ds['RAINC'].isel(Time=time_index) - ds['RAINC'].isel(Time=time_index-1)
rainnc = ds['RAINNC'].isel(Time=time_index) - ds['RAINNC'].isel(Time=time_index - 1)

# Format the datetime string
timestamp = pd.Timestamp(ds.XTIME[time_index].values)
formatted_time = timestamp.strftime('%Y-%m-%d %H.%M UTC')


plt.figure(figsize=(10, 10))
ax = plt.axes(projection=ccrs.PlateCarree())

# Add features to the map
ax.coastlines()
ax.add_feature(cfeature.LAND)
ax.add_feature(cfeature.OCEAN)
ax.gridlines(draw_labels=True)

(rainc+rainnc).plot(ax=ax, cmap='Blues', vmin=0, vmax=20, cbar_kwargs={'shrink': 0.5, 'pad': 0.1})

# Set plot title
plt.title(f'Precipitation at {formatted_time}')

plt.show()
