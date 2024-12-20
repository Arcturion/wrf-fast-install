# edited and taken from https://github.com/sagunkayastha/wrf_docker/blob/main/Dockerfile

FROM ubuntu:20.04

USER root
RUN apt-get update 

RUN apt-get install -yq tzdata && \
    ln -fs /usr/share/zoneinfo/Asia/Kathmandu /etc/localtime && \
    dpkg-reconfigure -f noninteractive tzdata 

# GCC CPP GFORTRAN
RUN apt-get update 
RUN apt-get install -y vim nano git bash unattended-upgrades --fix-missing
RUN apt-get install -y wget csh tar build-essential gfortran m4 zlib1g-dev

WORKDIR /Build_WRF/LIBRARIES
RUN wget -q https://www2.mmm.ucar.edu/wrf/OnLineTutorial/compile_tutorial/tar_files/mpich-3.0.4.tar.gz \
         https://www2.mmm.ucar.edu/wrf/OnLineTutorial/compile_tutorial/tar_files/netcdf-4.1.3.tar.gz \
         https://www2.mmm.ucar.edu/wrf/OnLineTutorial/compile_tutorial/tar_files/jasper-1.900.1.tar.gz \
         https://www2.mmm.ucar.edu/wrf/OnLineTutorial/compile_tutorial/tar_files/libpng-1.2.50.tar.gz \
         https://www2.mmm.ucar.edu/wrf/OnLineTutorial/compile_tutorial/tar_files/zlib-1.2.7.tar.gz 

# ## Install Libraries

ENV DIR=/Build_WRF/LIBRARIES CC=gcc CXX=g++ FC=gfortran FCFLAGS=-m64 F77=gfortran FFLAGS=-m64 JASPERLIB=$DIR/grib2/lib \
    JASPERINC=$DIR/grib2/include LDFLAGS=-L$DIR/grib2/lib CPPFLAGS=-I$DIR/grib2/include

# # ## NETCDF
RUN tar xzvf netcdf-4.1.3.tar.gz  && cd netcdf-4.1.3 &&\
    ./configure --prefix=$DIR/netcdf --disable-dap --disable-netcdf-4 --disable-shared &&\
    make &&\
    make install &&\
    cd ..
ENV PATH=$DIR/netcdf/bin/:$PATH
ENV NETCDF=$DIR/netcdf

## MPICH
RUN tar -zxvf mpich-3.0.4.tar.gz && cd mpich-3.0.4 &&\
    ./configure --prefix=$DIR/mpich &&\
    make &&\
    make install 
ENV PATH=$DIR/mpich/bin/:$PATH

## ZLIB
RUN tar -xzvf zlib-1.2.7.tar.gz  &&\
     cd zlib-1.2.7 &&\
    ./configure --prefix=$DIR/grib2 &&\
    make &&\
    make install 

## libpng
RUN tar -xzvf libpng-1.2.50.tar.gz && cd libpng-1.2.50 &&\
    ./configure --prefix=$DIR/grib2 &&\
    make &&\
    make install 

# Jasper
RUN tar -xzvf jasper-1.900.1.tar.gz  && cd jasper-1.900.1 &&\
    ./configure --prefix=$DIR/grib2 &&\
    make &&\
    make install 


ENV LD_LIBRARY_PATH=$DIR/grib2/lib:${LD_LIBRARY_PATH}

### WRF
ENV NETCDF_classic=1
WORKDIR /Build_WRF
RUN git clone https://github.com/wrf-model/WRF.git && cd WRF &&\     
    echo 34 | ./configure &&\
    ./compile em_real

ENV JASPERLIB=/Build_WRF/LIBRARIES/grib2/lib
ENV JASPERINC=/Build_WRF/LIBRARIES/grib2/include

# WPS
RUN git clone https://github.com/wrf-model/WPS.git && cd WPS &&\
    ./clean &&\
    echo 1 | ./configure &&\
    ./compile

RUN echo "wget https://www2.mmm.ucar.edu/wrf/src/wps_files/geog_high_res_mandatory.tar.gz" >> geog.sh &&\
    chmod +x geog.sh
