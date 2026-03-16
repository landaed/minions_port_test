# Embedded file name: mud\simulation\weather.pyo
from tgenative import *
from mud.tgepython.console import TGEExport
from mud.world.defines import *
import math

def SetWeatherDry(wc):
    if wc.precip < 0.7:
        try:
            rain = TGEObject('SweetRain')
            rain.delete()
            dust = TGEObject('SweetDust')
            dust.delete()
        except:
            pass

    else:
        try:
            rain = TGEObject('SweetRain')
            dust = TGEObject('SweetDust')
        except:
            TGEEval('\n              %rain = new Precipitation(SweetRain) {\n              dataBlock = "Sandstorm";\n              minSpeed = "1";\n              maxSpeed = "1";\n              minMass = "0.5";\n              maxMass = "1";\n              maxTurbulence = "10";\n              turbulenceSpeed = "0.1";\n              rotateWithCamVel = "0";\n              useTurbulence = "1";\n              numDrops = "1700";\n              boxWidth = "150";\n              boxHeight = "100";\n              doCollision = "0";\n\n          };\n           %dust = new Precipitation(SweetDust) {\n              position = "25.7111 -201.737 100.477";\n              rotation = "1 0 0 0";\n              scale = "1 1 1";\n              nameTag = "Dust";\n              dataBlock = "dustspecks";\n              minSpeed = "0.1";\n              maxSpeed = "0.7";\n              minMass = "1";\n              maxMass = "2";\n              maxTurbulence = "5";\n              turbulenceSpeed = "1";\n              rotateWithCamVel = "0";\n              useTurbulence = "1";\n              numDrops = "2600";\n              boxWidth = "200";\n              boxHeight = "100";\n              doCollision = "0";\n           };\n           MissionCleanup.add(%rain);\n           MissionCleanup.add(%dust);')


def SetWeatherCold(wc):
    if not wc.precip:
        try:
            rain = TGEObject('SweetRain')
            rain.delete()
        except:
            pass

    else:
        try:
            rain = TGEObject('SweetRain')
        except:
            TGEEval('\n             %rain = new Precipitation(SweetRain) {\n             datablock = "HeavySnow";\n             minSpeed = 0.01;\n             maxSpeed = 0.3;\n             numDrops = 5000;\n             boxWidth = 200;\n             boxHeight = 100;\n             minMass = 0.5;\n             maxMass = 1.5;\n             rotateWithCamVel = false;\n             doCollision = true;\n             useTurbulence = true;\n             maxTurbulence = 15.0;\n             turbulenceSpeed = 0.01;\n\n          };\n          MissionCleanup.add(%rain);')
            rain = TGEObject('SweetRain')

        rain.minSpeed = 0.05 + wc.windspeed * 0.3
        rain.maxSpeed = 0.3 + wc.windspeed * 0.5
        rain.setPercentage(wc.precip)
    if wc.precip < 0.8:
        try:
            light = TGEObject('SweetLightning')
            light.delete()
        except:
            pass

    else:
        try:
            lightning = TGEObject('SweetLightning')
        except:
            TGEEval('\n            %lightning = new Lightning(SweetLightning) {\n            position = "350 300 180";\n            scale = "250 400 500";\n            dataBlock = "LightningStorm";\n            strikesPerMinute = "10";\n            strikeWidth = "2.5";\n            chanceToHitTarget = "100";\n            strikeRadius = "50";\n            boltStartRadius = "20";\n            color = "1.000000 1.000000 1.000000 1.000000";\n            fadeColor = "0.100000 0.100000 1.000000 1.000000";\n            useFog = "0";\n            locked = "false";\n            };\n            MissionCleanup.add(%lightning);')


def SetWeatherTemperate(wc):
    if not wc.precip:
        try:
            rain = TGEObject('SweetRain')
            rain.delete()
        except:
            pass

    else:
        try:
            rain = TGEObject('SweetRain')
        except:
            TGEEval('\n             %rain = new Precipitation(SweetRain) {\n             datablock = "HeavyRain";\n             minSpeed = 2.5;\n             maxSpeed = 3.0;\n             numDrops = 5000;\n             boxWidth = 200;\n             boxHeight = 100;\n             minMass = 1.0;\n             maxMass = 1.2;\n             rotateWithCamVel = true;\n             doCollision = true;\n             useTurbulence = false;\n          };\n          MissionCleanup.add(%rain);')
            rain = TGEObject('SweetRain')

        rain.setPercentage(wc.precip)
    if wc.precip < 0.4:
        try:
            rain2 = TGEObject('SweetRainStorm')
            rain2.delete()
        except:
            pass

    else:
        try:
            rain2 = TGEObject('SweetRainStorm')
        except:
            TGEEval('\n             %rain = new Precipitation(SweetRainStorm) {\n             datablock = "HeavyRain2";\n             minSpeed = 2.5;\n             maxSpeed = 3.0;\n             numDrops = 1000;\n             boxWidth = 200;\n             boxHeight = 100;\n             minMass = 1.0;\n             maxMass = 1.2;\n             rotateWithCamVel = true;\n             doCollision = false;\n             useTurbulence = false;\n          };\n          MissionCleanup.add(%rain);')
            rain2 = TGEObject('SweetRainStorm')

        rain2.setPercentage(wc.precip)
    if wc.precip < 0.8:
        try:
            light = TGEObject('SweetLightning')
            light.delete()
        except:
            pass

    else:
        try:
            lightning = TGEObject('SweetLightning')
        except:
            TGEEval('\n            %rain =new Lightning(SweetLightning) {\n            position = "350 300 180";\n            scale = "250 400 500";\n            dataBlock = "LightningStorm";\n            strikesPerMinute = "10";\n            strikeWidth = "2.5";\n            chanceToHitTarget = "100";\n            strikeRadius = "50";\n            boltStartRadius = "20";\n            color = "1.000000 1.000000 1.000000 1.000000";\n            fadeColor = "0.100000 0.100000 1.000000 1.000000";\n            useFog = "0";\n            locked = "false";\n            };\n            MissionCleanup.add(%rain);')


def SetWeather(wc):
    sky = TGEObject('sky')
    sky.setCloudCover(wc.cloudCover)
    d = math.radians(wc.winddir)
    x = math.sin(d)
    y = math.cos(d)
    sky.setWindVelocity(x * wc.windspeed, y * wc.windspeed, 0)
    try:
        if int(TGEGetGlobal('$pref::DisableWeatherEffects')):
            return
    except:
        pass

    if wc.climate == RPG_CLIMATE_TROPICAL or wc.climate == RPG_CLIMATE_TEMPERATE:
        SetWeatherTemperate(wc)
    if wc.climate == RPG_CLIMATE_COLD or wc.climate == RPG_CLIMATE_POLAR:
        SetWeatherCold(wc)
    if wc.climate == RPG_CLIMATE_DRY:
        SetWeatherDry(wc)