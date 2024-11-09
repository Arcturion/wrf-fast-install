import xarray as xr
import glob

# Specify the pattern for WRF output files
file_pattern = 'wrfout_d01_2024-11*'

# Find all matching files
files = glob.glob(file_pattern)

# Create an empty list to store datasets
datasets = []

# Iterate over each file
for file in files:
    # Open the dataset
    ds = xr.open_dataset(file)

    # Select the desired variables
    ds = ds[['RAINC', 'RAINNC']]

    # Append the dataset to the list
    datasets.append(ds)

# Concatenate all datasets along the time dimension
combined_ds = xr.concat(datasets, dim='Time')

# Save the combined dataset as a NetCDF file
combined_ds.to_netcdf('combined_wrf_output.nc')
