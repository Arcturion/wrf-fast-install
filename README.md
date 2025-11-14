
# WRF Docker Setup Fast Install

This repository provides a Dockerized setup for running the Weather Research and Forecasting (WRF) model. Follow the instructions below to install dependencies, clone this repository, and get the container running.

## Prerequisites

Ensure that you have the following installed on your system:
- **Git**
- **Docker**





## Installation WRF only

### Step 1: Update and Install Git

Start by updating your system's package list and installing Git.

```bash
sudo apt update
sudo apt install git
```

### Step 2: Clone the Repository

Clone this repository using the following command:

```bash
git clone https://github.com/Arcturion/wrf-fast-install.git
```

### Step 3: Install Docker (if not already installed)

Make sure Docker is installed on your system. 
```bash
docker --version
```

to install, follow this code
```bash
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh
```

Then, check again
```bash
docker --version
```

If exist, activate and test
```bash
dockerd &
```

```bash
docker run hello-world
```

### Step 4: Build the Docker Image

Navigate into the cloned repository directory and build the Docker image with the following command:

```bash
cd wrf-fast-install
docker build -t wrf-fast-install .
```

### Step 5: Run the Docker Container

Once the image has been built, run the container interactively:

```bash
docker run -it wrf-fast-install
```

You should now be inside the Docker container, ready to proceed with WRF.


## Installation WRFDA

### Step 1: Build the WRF Only fiorst
```bash
git clone https://github.com/Arcturion/wrf-fast-install.git
cd wrf-fast-install
docker build -t wrf-fast-install .
```

### Step 2: Build the WRF DA image
download the WRFDA tarball first (WRFDAV3.9.TAR.gz)
```bash
docker build -f Dockerfile.wrfda -t wrf-wrfda .
```

### Step 5: Run the Docker Container

Once the image has been built, run the container interactively:

```bash
docker run -it wrf-wrfda /bin/bash
```
Inside the container you should have da_wrfvar (and others) on the PATH if the build succeeded.



## Additional Information

- **Repository**: This repository contains the necessary files and Docker configurations to set up and run the WRF model.
- **License**: No License, everyone can use it !
- **Contact**: For any questions, feel free to reach out to my twitter @pradanadimass.

