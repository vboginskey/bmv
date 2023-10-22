import asyncio
import logging
import os
import time
from functools import partial
from bleak import BleakClient, BleakScanner, uuids
from bleak.backends.characteristic import BleakGATTCharacteristic
from influxdb import InfluxDBManager

from ut1300 import UT1300

NUM_BATTERIES=4

async def discover_batteries():
    batteries = {}

    service_uuids=[uuids.normalize_uuid_16(uuid) for uuid in UT1300.DEVICE_SERVICE_UUIDS]

    logging.info("starting discovery...")
    async with BleakScanner(service_uuids=service_uuids) as scanner:
        async for device, advertisement_data in scanner.advertisement_data():
            if advertisement_data.local_name is None:
                continue

            logging.info("discovered %s", advertisement_data.local_name)
            if any(name in advertisement_data.local_name for name in UT1300.DEVICE_LOCAL_NAMES):
                batteries[advertisement_data.local_name] = device
            if len(batteries) == NUM_BATTERIES:
                break

    return [UT1300(name, device) for name, device in batteries.items()]

async def parse_response(battery: UT1300, influx: InfluxDBManager, sender: BleakGATTCharacteristic, data: bytearray):
    fields = battery.parse_data(data)
    if fields is not None:
        await influx.write({
            "measurement": "battery",
            "tags": { "name": battery.name },
            "fields": fields,
            "time": int(time.time() * 1e9)
        })


async def monitor_and_report(battery, influx):
    logging.info("running monitoring loop...")
    characteristic = uuids.normalize_uuid_16(UT1300.CHARACTERISTIC_UUID)
    callback = partial(parse_response, battery, influx)

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
    influxdb_url = os.environ["INFLUXDB_URL"]
    influxdb_token = os.environ["INFLUXDB_TOKEN"]
    influxdb_org = os.environ["INFLUXDB_ORG"]
    influxdb_bucket = os.environ["INFLUXDB_BUCKET"]

    batteries = await discover_batteries()

    async with InfluxDBManager(influxdb_url, influxdb_token, influxdb_org, influxdb_bucket) as influx:
        async with asyncio.TaskGroup() as tg:
            for battery in batteries:
                tg.create_task(monitor_and_report(battery, influx))
                tg.create_task(report_successes(battery))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)-15s %(name)-8s %(levelname)s: %(message)s",
)

asyncio.run(main())
