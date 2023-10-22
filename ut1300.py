import logging

from enum import Enum

class UT1300:
    DEVICE_LOCAL_NAMES = ["R1300SJ", "UT1300 BT"]
    DEVICE_SERVICE_UUIDS = [0xfee7, 0xffe0]
    CHARACTERISTIC_UUID = 0xffe1
    PACKET_PREFIX_LENGTH = 4

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
        self.successes = {
            "cell_voltages": 0,
            "battery_pack_info": 0,
            "current_and_temperature": 0
        }
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

    def parse_data(self, data):
        is_start_of_message = len(data) > 2 and data[0] == 0xea and data[1] == 0xd1
        if is_start_of_message:
            self.accumulated_data = data
        elif self.accumulated_data:
            self.accumulated_data += data

        is_min_length = len(self.accumulated_data) >= 8
        if not is_min_length:
            return

        is_complete_message = self.accumulated_data[-1] == 0xf5
        is_correct_length = self.accumulated_data[3] + self.PACKET_PREFIX_LENGTH == len(self.accumulated_data)
        if not is_complete_message or not is_correct_length:
            return

        if self.accumulated_data[5] == 0x02:
            return self.parse_cell_voltages()
        elif self.accumulated_data[5] == 0x03:
            return self.parse_battery_pack_info()
        elif self.accumulated_data[5] == 0x04:
            return self.parse_current_and_temperature()


    def parse_cell_voltages(self):
        self.cell1_voltage = float((self.accumulated_data[9] << 8) + self.accumulated_data[10]) / 1000.0
        self.cell2_voltage = float((self.accumulated_data[11] << 8) + self.accumulated_data[12]) / 1000.0
        self.cell3_voltage = float((self.accumulated_data[13] << 8) + self.accumulated_data[14]) / 1000.0
        self.cell4_voltage = float((self.accumulated_data[15] << 8) + self.accumulated_data[16]) / 1000.0

        self.successes["cell_voltages"] += 1
        logging.debug("%s: Updated cell voltages", self.device.name)

        return {
            "cell1_voltage": self.cell1_voltage,
            "cell2_voltage": self.cell2_voltage,
            "cell3_voltage": self.cell3_voltage,
            "cell4_voltage": self.cell4_voltage
        }

    def parse_battery_pack_info(self):
        if self.accumulated_data[6] == 0x31:
            self.battery_state = UT1300.State.DISCHARGING
        elif self.accumulated_data[6] == 0x32:
            self.battery_state = UT1300.State.CHARGING
        else:
            self.battery_state = UT1300.State.UNKNOWN

        self.current = float((self.accumulated_data[7] << 8) + self.accumulated_data[8]) / 100.0
        self.temperature1 = (self.accumulated_data[14] - 40) * 9 / 5 + 32
        self.temperature2 = (self.accumulated_data[15] - 40) * 9 / 5 + 32
        self.mosfet_temperature = (self.accumulated_data[16] - 40) * 9 / 5 + 32
        self.ambient_temperature = (self.accumulated_data[17] - 40) * 9 / 5 + 32

        self.successes["battery_pack_info"] += 1
        logging.debug("%s: Updated battery pack info", self.device.name)

        return {
            "current": self.current,
            "temperature1": self.temperature1,
            "temperature2": self.temperature2,
            "mosfet_temperature": self.mosfet_temperature,
            "ambient_temperature": self.ambient_temperature
        }

    def parse_current_and_temperature(self):
        self.cycle_count = self.accumulated_data[6]
        self.state_of_charge = self.accumulated_data[7]
        self.full_capacity = float((0x01 << 16) + (self.accumulated_data[21] << 8) + self.accumulated_data[22]) / 1000.0
        self.remaining_capacity = float((self.accumulated_data[27] << 8) + self.accumulated_data[28]) / 1000.0
        self.discharge_time_left = float((self.accumulated_data[30] << 8) + self.accumulated_data[31])
        self.charge_time_left = float((self.accumulated_data[33] << 8) + self.accumulated_data[34])
        self.total_voltage = float((self.accumulated_data[47] << 8) + self.accumulated_data[48]) / 100.0
        self.max_cell_voltage = float((self.accumulated_data[49] << 8) + self.accumulated_data[50]) / 1000.0
        self.min_cell_voltage = float((self.accumulated_data[51] << 8) + self.accumulated_data[52]) / 1000.0

        self.successes["current_and_temperature"] += 1
        logging.debug("%s: Updated current and temperatures", self.device.name)

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

    def report_successes(self):
        logging.info("Success counters:\nCell voltages: %s\nBattery pack info:%s\nCurrent and temperature: %s",
                    self.successes["cell_voltages"],
                    self.successes["battery_pack_info"],
                    self.successes["current_and_temperature"])
