# Name:         gridmet_ee_pull.py
# Purpose:      Pulls Daily GRIDMET data for ETDemands model input (input file with Lat, Lon, SCENE_ID? required)
# Author:       Chris Pearson
# Created       2017-12-04
# Python:       2.7
#--------------------------------
#import csv
import pandas as pd
import datetime as dt
import os
import ee
import numpy as np
#import math
import logging
from time import sleep
import timeit

ee.Initialize()

system_properties = ['system:index', 'system:time_start', 'system:time_end']

# Change working directory
os.chdir('Z:\USBR_UC_ET_Feasability_Study\ETDemands\et-demands\upper_co\climate')

#Run RefET on imported dataset
RefET_flag=True
if RefET_flag: 
    import RefET

#Input .csv containing Lat, Lon, and 
input_df = pd.read_csv('gridmet_4km_20sites.csv')

#Specify column order for output .csv Variables: 'Date','Year','Month','Day','Tmax','Tmin','Srad','Ws_10m','q','Prcp','ETo'
output_order=['Date','Year','Month','Day','Tmax_C','Tmin_C','Srad','Ws_2m','q','Prcp','ETo']

# Date Range to Retrieve Values (start=inclusive, end=exclusive)
start_date='1979-01-01'
end_date='2018-01-01'

#List of ee GRIDMET varibles to retrieve
met_bands = ['tmmx', 'tmmn', 'srad', 'vs', 'sph', 'pr','pet']
#The GRIDMET dataset contains the following bands:
#
#pr: precipitation amount (mm, daily total)
#rmax: maximum relative humidity (%)
#rmin: minimum relative humidity (%)
#sph: specific humidity (kg/kg)
#srad: surface downward shortwave radiation (W/m^2)
#th: wind direction (degrees clockwise from north)
#tmmn: minimum temperature (K)
#tmmx: maximum temperature (K)
#vs: wind velocity at 10 m (m/s)
#erc: energy release component (NFDRS fire danger index)
#pet: potential evapotranspiration (mm)
#bi: burning index (NFDRS fire danger index)
#fm100: 100-hour dead fuel moisture (%)
#fm1000: 1000-hour dead fuel moisture (%)



#Rename GRIDMENT variables
met_names= ['Tmax', 'Tmin', 'Srad', 'Ws_10m', 'q', 'Prcp','ETo']

class flushfile():
    def __init__(self, f):
        self.f = f

    def __getattr__(self, name):
        return object.__getattribute__(self.f, name)

    def write(self, x):
        self.f.write(x)
        self.f.flush()

    def flush(self):
        self.f.flush()
flushfile = flushfile


#Exponential getinfo call from ee-tools/utils.py
def ee_getinfo(ee_obj, n=30):
    """Make an exponential backoff getInfo call on the Earth Engine object"""
    output = None
    for i in range(1, n):
#        print(i)
        try:
            output = ee_obj.getInfo()
        except Exception as e:
            print('    Resending query ({}/10)'.format(i))
            print('    {}'.format(e))
            sleep(i ** 2)
        if output:
            break
    return output

#%%
#Loop through dataframe row by row and grab desired met data from GRID collections based on Lat/Lon and Start/End dates#
for index, row in input_df.iterrows():
    start_time=timeit.default_timer()
    #Limit iteration during development#
    if index < 1:
        continue
#    if index > 0:
#        break
    lat = row.LAT
    lon = row.LON

    GRIDMET_ID_str=str(row.GRIDMET_ID)
    print(['Cell Loop Counter',index+1])
    print(['GRIDMET ID:',row.GRIDMET_ID])

    point = ee.Geometry.Point(lon,lat);
    
    #Loop through ee pull by year (max 5000 records for getInfo()
    #Append each new year on end of dataframe
    #Process dataframe units and output after                        
    start_date_yr=dt.datetime.strptime(start_date,'%Y-%m-%d').year
    end_date_yr=dt.datetime.strptime(end_date,'%Y-%m-%d').year                             
    for iter_year in range(start_date_yr, end_date_yr+1, 1):
        print(iter_year)                               
    #Filter Collection by Start/End Date and Lat/Lon Point#
        gridmet_coll = ee.ImageCollection('IDAHO_EPSCOR/GRIDMET') \
                .filterDate(start_date, end_date) \
                .filter(ee.Filter.calendarRange(iter_year, iter_year, 'year')) \
                .select(met_bands,met_names)
    
    
        def get_values(image):
            #Pull out Date from Image
            dateStr = image.date();
            dateNum = ee.Image.constant(ee.Number.parse(dateStr.format("YYYYMMdd"))).rename(['Date'])
            #Add Desired Date Band to Image
            image = image.addBands([dateNum])      
            #Reduce image taking mean of all pixels in polygon#
            input_mean = ee.Image(image) \
                .reduceRegion(
                        reducer = ee.Reducer.mean(), geometry=point, scale = 4000)
            return ee.Feature(None, input_mean)   
        #Run get_values fuction over all images gridmet collection
        data=gridmet_coll.map(get_values)
    #    print(data.getInfo())
    
    #   Export dictionary to pandas dataframe using expornential getInfo fnc
        if iter_year==start_date_yr:
                export_df = pd.DataFrame([
                        ftr['properties']
                        for ftr in ee_getinfo(data)['features']])
        else:
                export_df2 = pd.DataFrame([
                ftr['properties']
                for ftr in ee_getinfo(data)['features']])
                export_df=export_df.append(export_df2)    
    #Reset Index
    export_df=export_df.reset_index(drop=False)
#    break

    #Convert dateNum to datetime and create Year, Month, Day
    export_df.Date = pd.to_datetime(export_df.Date.astype(str), format='%Y%m%d')
    export_df['Year']=export_df['Date'].dt.year
    export_df['Month']=export_df['Date'].dt.month
    export_df['Day']=export_df['Date'].dt.day       
    export_df['DOY']=export_df['Date'].dt.dayofyear 
             
    #Remove all negative Prcp values (GRIDMET Bug)
    export_df.Prcp=export_df.Prcp.clip(lower=0)       

    #Convert 10m windspeed to 2m
    zw=10
    export_df['Ws_2m']=export_df.Ws_10m*((4.87/np.log(67.8*zw-5.42)))
#    export_df.rename(columns={'Ws_10m': 'Ws_2m'}, inplace=True)

    #Unit Conversions
    export_df.Tmax=export_df.Tmax-273.15; #K to C
    export_df.Tmin=export_df.Tmin-273.15; #K to C
    export_df.rename(columns={'Tmax': 'Tmax_C','Tmin':'Tmin_C'}, inplace=True)
      
    if RefET_flag: 
        #Create RefET Specific Dataframe
        ref_df=pd.DataFrame()
        ref_df['Date']=export_df.Date
        ref_df['DOY']=export_df.DOY      
        #Temperature Min/Max (C)
        ref_df['Tmin']=export_df['Tmin_C']
        ref_df['Tmax']=export_df['Tmax_C']
        
        #Pressure from elevation (ASCE Eqn. 34) kPa
        P= 101.3*((293.15-0.0065*input_df.ELEV_M[0])/293.15)**5.26            
        #Specific Humidity to Vapor Pressure and elevation-based pressure kPa
        ref_df['ea']=export_df.q*P/(0.622+0.378*export_df.q)      
              
        #Srad to MJ m-2 day-1
        ref_df['Srad_MJ']=0.0864*export_df.Srad
              
        #Windspeed Sensor Ht (m)      
        ref_df['Ws_10m']=export_df.Ws_10m          
              
        #Windspeed Sensor Ht (m)      
        ref_df['Sensor_Ht']=zw      
        
        #Elevation (m)                
        ref_df['ELEV_M']=input_df.ELEV_M[0]
        
        #Latitude (Radians)
        ref_df['LAT_rad']=lat*np.pi/180
               
        #Run RefET code on ref_df dataframe
        ref_df['ETr']= RefET.daily(ref_df.Tmin, ref_df.Tmax, ref_df.ea, ref_df.Srad_MJ, ref_df.Ws_10m, ref_df.Sensor_Ht, ref_df.ELEV_M, ref_df.LAT_rad, ref_df.DOY, ref_type='etr',
              rso_type='full', rso=None)
        ref_df['ETo_py']= RefET.daily(ref_df.Tmin, ref_df.Tmax, ref_df.ea, ref_df.Srad_MJ, ref_df.Ws_10m, ref_df.Sensor_Ht, ref_df.ELEV_M, ref_df.LAT_rad, ref_df.DOY, ref_type='eto',
              rso_type='full', rso=None)
        
        #Copy Relevant ETr/Eto data to export_df
        export_df['ETr']=ref_df.ETr
        
        output_order=['Date','Year','Month','Day','Tmax_C','Tmin_C','Srad','Ws_2m','q','Prcp','ETo','ETr']
    
    #Output Filename with GRIDMET ID
    output_name=['gridmet_historical_'+GRIDMET_ID_str+'.csv']
    
    #Write csv files to working directory
    export_df.to_csv(output_name[0],columns=output_order)

    elapsed=timeit.default_timer() - start_time
    print(elapsed)
    
    #%% Test Plotting ETo Comparison    
    import seaborn as sns
    import matplotlib.pyplot as plt
    sns.set(font_scale=2.5)
    g = sns.jointplot(x=export_df.ETo, y=ref_df.ETo_py)
  
    export_df.set_index('Date', inplace=True)
    ref_df.set_index('Date', inplace=True)
    
    export_df['ETo'].plot(color='b')
    ref_df['ETo_py'].plot(color='r')
    plt.xlabel('', fontsize=20)
    plt.ylabel('E (mm)', fontsize=20)
    plt.legend(['GRIDMET ETo', 'Python ETo'],fontsize=20)

    
   
