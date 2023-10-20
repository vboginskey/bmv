import asyncio
import logging

from bleak import BleakClient, BleakScanner, uuids
from bleak.backends.characteristic import BleakGATTCharacteristic
from functools import partial
from ut1300 import UT1300

logger = logging.getLogger(__name__)

NUM_BATTERIES=4

async def discover_batteries():
    batteries = {}

    service_uuids=[uuids.normalize_uuid_16(uuid) for uuid in UT1300.DEVICE_SERVICE_UUIDS]

    logger.info("starting discovery...")
    async with BleakScanner(service_uuids=service_uuids) as scanner:
        async for device, advertisement_data in scanner.advertisement_data():
            if advertisement_data.local_name is None:
                break

            logger.info("discovered %s", advertisement_data.local_name)
            if any(name in advertisement_data.local_name for name in UT1300.DEVICE_LOCAL_NAMES):
                batteries[device.address] = device
            if len(batteries) == NUM_BATTERIES:
                break

    return [UT1300(battery) for battery in batteries.values()]

def parse_response(battery: UT1300, sender: BleakGATTCharacteristic, data: bytearray):
    battery.parse_data(data)

async def run_loop(battery):
    logger.info("running monitoring loop...")
    characteristic = uuids.normalize_uuid_16(UT1300.CHARACTERISTIC_UUID)
    callback = partial(parse_response, battery)

    async with BleakClient(battery.device) as client:
        await client.start_notify(characteristic, callback)
        while True:
            await client.write_gatt_char(characteristic, UT1300.COMMANDS["REQUEST_CELL_VOLTAGES"], response=True)
            await asyncio.sleep(2.0)
            await client.write_gatt_char(characteristic, UT1300.COMMANDS["REQUEST_BATTERY_PACK_INFO"], response=True)
            await asyncio.sleep(2.0)
            await client.write_gatt_char(characteristic, UT1300.COMMANDS["REQUEST_CURRENT_AND_TEMPERATURE"], response=True)
            await asyncio.sleep(2.0)

async def report_successes(battery):
    while True:
        await asyncio.sleep(30.0)
        battery.report_successes()

async def main():
    batteries = await discover_batteries()

    async with asyncio.TaskGroup() as tg:
        for battery in batteries:
            tg.create_task(run_loop(battery))
            tg.create_task(report_successes(battery))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)-15s %(name)-8s %(levelname)s: %(message)s",
)

asyncio.run(main())
