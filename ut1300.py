import logging
from enum import Enum


class UT1300:
    DEVICE_LOCAL_NAMES = ["R1300SJ", "UT1300 BT"]
    DEVICE_SERVICE_UUIDS = [0xfee7, 0xffe0]
    CHARACTERISTIC_UUID = 0xffe1

    COMMANDS = {
        "REQUEST_CELL_VOLTAGES": b'\xea\xd1\x01\x04\xff\x02\xf9\xf5',
        "REQUEST_BATTERY_PACK_INFO": b'\xea\xd1\x01\x04\xff\x03\xf8\xf5',
        "REQUEST_CURRENT_AND_TEMPERATURE": b'\xea\xd1\x01\x04\xff\x04\xff\xf5'
    }

    class State(Enum):
        CHARGING = 1
        DISCHARGING = 2
        UNKNOWN = 3

    def __init__(self, name, device):
        self.name = name
        self.device = device
        self.cell1_voltage = 0.0
        self.cell2_voltage = 0.0
        self.cell3_voltage = 0.0
        self.cell4_voltage = 0.0
        self.cycle_count = 0
        self.state_of_charge = 0
        self.full_capacity = 0.0
        self.remaining_capacity = 0.0
        self.battery_state = UT1300.State.UNKNOWN
        self.current = 0.0
        self.temperature1 = 0
        self.temperature2 = 0
        self.mosfet_temperature = 0
        self.ambient_temperature = 0
        self.discharge_time_left = 0.0
        self.charge_time_left = 0.0
        self.total_voltage = 0.0
        self.max_cell_voltage = 0.0
        self.min_cell_voltage = 0.0

        self.accumulated_data = bytearray()
        self.successes = {
            "cell_voltages": 0,
            "battery_pack_info": 0,
            "current_and_temperature": 0
        }

    def ingest_data(self, data):
        if self._is_start_of_message(data):
            self.accumulated_data = data
        elif self.accumulated_data:
            self.accumulated_data += data

        if not self._is_valid_message():
            return

        return self._parse_message()

    def report_successes(self):
        logging.info("Success counters:\n:"
                     "Cell voltages: %s\n"
                     "Battery pack info:%s\n"
                     "Current and temperature: %s",
                     self.successes["cell_voltages"],
                     self.successes["battery_pack_info"],
                     self.successes["current_and_temperature"])

    def _is_start_of_message(self, data):
        start_byte_1 = 0xea
        start_byte_2 = 0xd1

        return len(data) > 2 and data[0] == start_byte_1 and data[1] == start_byte_2

    def _is_valid_message(self):
        if not (self._is_message_min_length() and
                self._is_complete_message() and
                self._is_correct_length):
            return False

        return True

    def _is_message_min_length(self):
        return len(self.accumulated_data) >= 8

    def _is_complete_message(self):
        end_byte = 0xf5

        return self.accumulated_data[-1] == end_byte

    def _is_correct_length(self):
        packet_prefix_length = 4

        return self.accumulated_data[3] + packet_prefix_length == len(self.accumulated_data)

    def _parse_message(self):
        if self.accumulated_data[5] == 0x02:
            return self._parse_cell_voltages()
        elif self.accumulated_data[5] == 0x03:
            return self._parse_current_and_temperature()
        elif self.accumulated_data[5] == 0x04:
            return self._parse_battery_pack_info()

    def _parse_cell_voltages(self):
        self.cell1_voltage = float(
            (self.accumulated_data[9] << 8) + self.accumulated_data[10]) / 1000.0
        self.cell2_voltage = float(
            (self.accumulated_data[11] << 8) + self.accumulated_data[12]) / 1000.0
        self.cell3_voltage = float(
            (self.accumulated_data[13] << 8) + self.accumulated_data[14]) / 1000.0
        self.cell4_voltage = float(
            (self.accumulated_data[15] << 8) + self.accumulated_data[16]) / 1000.0

        self.successes["cell_voltages"] += 1
        self.accumulated_data = bytearray()

        return {
            "cell1_voltage": self.cell1_voltage,
            "cell2_voltage": self.cell2_voltage,
            "cell3_voltage": self.cell3_voltage,
            "cell4_voltage": self.cell4_voltage
        }

    def _parse_current_and_temperature(self):
        self.current = float(
            (self.accumulated_data[7] << 8) + self.accumulated_data[8]) / 100.0

        if self.accumulated_data[6] == 0x31:
            self.battery_state = UT1300.State.DISCHARGING
            self.current = -self.current
        elif self.accumulated_data[6] == 0x32:
            self.battery_state = UT1300.State.CHARGING
        else:
            self.battery_state = UT1300.State.UNKNOWN

        self.temperature1 = self.accumulated_data[14] - 40
        self.temperature2 = self.accumulated_data[15] - 40
        self.mosfet_temperature = self.accumulated_data[16] - 40
        self.ambient_temperature = self.accumulated_data[17] - 40

        self.successes["current_and_temperature"] += 1
        self.accumulated_data = bytearray()

        return {
            "current": self.current,
            "temperature1": self.temperature1,
            "temperature2": self.temperature2,
            "mosfet_temperature": self.mosfet_temperature,
            "ambient_temperature": self.ambient_temperature
        }

    def _parse_battery_pack_info(self):
        self.cycle_count = self.accumulated_data[6]
        self.state_of_charge = self.accumulated_data[7]
        self.full_capacity = float(
            (0x01 << 16) + (self.accumulated_data[21] << 8) + self.accumulated_data[22]) / 1000.0
        self.remaining_capacity = float(
            (self.accumulated_data[27] << 8) + self.accumulated_data[28]) / 1000.0
        self.discharge_time_left = float(
            (self.accumulated_data[30] << 8) + self.accumulated_data[31])
        self.charge_time_left = float(
            (self.accumulated_data[33] << 8) + self.accumulated_data[34])
        self.total_voltage = float(
            (self.accumulated_data[47] << 8) + self.accumulated_data[48]) / 100.0
        self.max_cell_voltage = float(
            (self.accumulated_data[49] << 8) + self.accumulated_data[50]) / 1000.0
        self.min_cell_voltage = float(
            (self.accumulated_data[51] << 8) + self.accumulated_data[52]) / 1000.0

        self.successes["battery_pack_info"] += 1
        self.accumulated_data = bytearray()

        return {
            "cycle_count": self.cycle_count,
            "state_of_charge": self.state_of_charge,
            "full_capacity": self.full_capacity,
            "remaining_capacity": self.remaining_capacity,
            "discharge_time_left": self.discharge_time_left,
            "charge_time_left": self.charge_time_left,
            "total_voltage": self.total_voltage,
            "max_cell_voltage": self.max_cell_voltage,
            "min_cell_voltage": self.min_cell_voltage
        }
