from __future__ import print_function
import datetime
import json
import logging
import os
import sys
import time
import traceback

from aqi.calculator import AQICalculator
from aqi.instruction_set import SensorInstructionSet
from aqi import measurement_modes
from aqi.reading import Reading


logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)

READINGS_FILE = 'readings.json'


class AirQualitySensor:

    modes = measurement_modes.modes
    logger = logging.getLogger(__name__)

    def __init__(self, mode='hourly_five_minute_average', mock=False):
        self.mode = self.modes[mode]
        self.instruction_set = SensorInstructionSet(mock=mock)
        self.calculator = AQICalculator()
        self.readings = []

    def __enter__(self):
        self.logger.debug('Entering sensor context.')
        self.instruction_set.wake()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.logger.debug('Exiting sensor context.')

        if exc_type:
            self.logger.error('Exception occurred: %s, %s, %s', exc_type, exc_val, exc_tb)
            traceback.print_tb(exc_tb)

        self.instruction_set.sleep()
        self.save_readings_to_file(READINGS_FILE)

    def monitor(self):
        """ Monitor the air quality according to the mode selected.

        :return None:
        """
        print(self.mode)

        start_time = datetime.datetime.now()

        with self:
            if self.mode.sleep_time == 0:

                self.logger.debug('Starting continuous infinite loop.')
                while True:

                    if not self.mode.night_monitoring:

                        if self.is_night():
                            continue

                        self.take_reading()

                    else:
                        self.take_reading()

            else:

                self.logger.debug('Starting non-continuous infinite loop.')
                while True:

                    if not self.mode.night_monitoring:

                        if self.is_night():
                            continue

                        if self.mode.monitoring_duration:
                            start_time = self._carry_out_monitoring_cycle(start_time)
                        else:
                            self.take_reading()

                    else:
                        if self.mode.monitoring_duration:
                            start_time = self._carry_out_monitoring_cycle(start_time)
                        else:
                            self.take_reading()

    def _carry_out_monitoring_cycle(self, start_time):
        """ Carry out one monitoring cycle of a monitoring period.

        :param datetime.datetime start_time:
        :return datetime.datetime:
        """
        self.logger.debug('Carrying out one monitoring cycle.')

        time_spent_monitoring = datetime.datetime.now() - start_time

        if time_spent_monitoring < self.mode.monitoring_duration:
            self.take_reading()

        else:
            self.aggregate_readings()
            self.save_readings_to_file(READINGS_FILE)
            self.instruction_set.sleep()
            time.sleep(self.mode.sleep_time)
            self.instruction_set.wake()
            start_time = datetime.datetime.now()

        return start_time

    def take_reading(self):
        """ Take a reading of the air quality.

        :return None:
        """
        self.logger.debug('Taking a reading.')
        reading = self.calculator.calculate_aqis_and_bands(self.instruction_set.query_data())
        self.readings.append(reading)
        print(reading.to_dict())
        time.sleep(self.mode.measurement_period)

    def aggregate_readings(self):
        """ Aggregate readings according to the measurement mode.

        :return None:
        """
        self.logger.debug('Aggregating readings.')

        if not self.mode.aggregation:
            return

        if self.mode.aggregation == 'mean':
            raw_average_reading = {
                'time': self.readings[0].time + (self.readings[0].time + self.readings[-1].time) / 2,
                'pm25': sum(reading.pm25 for reading in self.readings),
                'pm10': sum(reading.pm10 for reading in self.readings)
            }

            self.readings = [self.calculator.calculate_aqis_and_bands(raw_average_reading)]

    def is_night(self):
        """ Is it night-time?

        :return bool:
        """
        now = datetime.datetime.now().time()
        night_start = datetime.time(hour=21)
        night_end = datetime.time(hour=9, minute=30)
        return now >= night_start and now < night_end

    def save_readings_to_file(self, path):
        """ Save readings to a file, appending to any readings already in the file.

        :param str path:
        :return None:
        """
        if not os.path.exists(path):
            self.logger.debug('File at %s not found; creating file', path)
            open(path, 'w+').close()

        with open(path, 'r') as f:
            try:
                self.logger.debug('Opening file at %s', path)
                existing_data = [Reading.from_dict(reading) for reading in json.load(f)]
            except:
                self.logger.debug('Data in file is corrupt; resetting to empty list')
                existing_data = []

        all_data = existing_data + self.readings

        with open(path, 'w') as f:
            self.logger.debug('Writing file to %s', path)
            json.dump([reading.to_dict() for reading in all_data], f)

        self.readings = []


if __name__ == '__main__':
    AirQualitySensor(mode='ten_second_alternation').monitor()
