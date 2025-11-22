from api.models import AirExposureLog
from api.services.services import get_current_weather


def update_air_exposure_log_with_weather(air_exposure_log: AirExposureLog):
    if air_exposure_log is None:
        return None
    if air_exposure_log.temperature is not None:
        return air_exposure_log
    current_weather = get_current_weather(
        air_exposure_log.latitude, air_exposure_log.longitude
    )
    air_exposure_log.temperature = current_weather["temp_c"]
    air_exposure_log.humidity = current_weather["humidity"]
    air_exposure_log.pressure = current_weather["pressure"]
    air_exposure_log.uvi = current_weather["uvi"]
    air_exposure_log.uvi_level = current_weather["uvi_level"]
    air_exposure_log.save()
    return air_exposure_log
