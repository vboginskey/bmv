import asyncio
import logging

from bleak import BleakClient, BleakScanner, uuids
from bleak.backends.characteristic import BleakGATTCharacteristic

from functools import partial

from ut1300 import UT1300

NUM_BATTERIES=4

async def discover_batteries():
    batteries = {}

    service_uuids=[uuids.normalize_uuid_16(uuid) for uuid in UT1300.DEVICE_SERVICE_UUIDS]

    async with BleakScanner(service_uuids=service_uuids) as scanner:
        async for device, advertisement_data in scanner.advertisement_data():
            if advertisement_data.local_name is None:
                break

            logging.info("discovered %s", advertisement_data.local_name)
            if any(name in advertisement_data.local_name for name in UT1300.DEVICE_LOCAL_NAMES):
                batteries[device.address] = device
            if len(batteries) == NUM_BATTERIES:
                break

    return list(batteries.values())

def parse_response(battery: UT1300, sender: BleakGATTCharacteristic, data: bytearray):
    battery.parse_data(data)

async def main():
    batteries = await discover_batteries()

    battery = UT1300(batteries[0])

    async with BleakClient(battery.device) as client:
        characteristic = uuids.normalize_uuid_16(UT1300.CHARACTERISTIC_UUID)
        callback = partial(parse_response, battery)
        await client.start_notify(characteristic, callback)
        await client.write_gatt_char(characteristic, UT1300.COMMANDS["REQUEST_CELL_VOLTAGES"], response=True)
        await asyncio.sleep(1.0)
        await client.write_gatt_char(characteristic, UT1300.COMMANDS["REQUEST_BATTERY_PACK_INFO"], response=True)
        await asyncio.sleep(1.0)
        await client.write_gatt_char(characteristic, UT1300.COMMANDS["REQUEST_CURRENT_AND_TEMPERATURE"], response=True)
        await asyncio.sleep(5.0)
        await client.stop_notify(uuids.normalize_uuid_16(UT1300.CHARACTERISTIC_UUID))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)-15s %(name)-8s %(levelname)s: %(message)s",
)
asyncio.run(main())
