import asyncio
import logging
import os
import subprocess
import time
from functools import partial
from bleak import BleakClient, BleakScanner, uuids
from bleak.assigned_numbers import AdvertisementDataType
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.backends.bluezdbus.advertisement_monitor import OrPattern
from bleak.backends.bluezdbus.scanner import BlueZScannerArgs
from victron_ble.devices import BatteryMonitor
from influxdb import InfluxDBManager

from ut1300 import UT1300
from utils import SharedCounter

NUM_BATTERIES = 4
COMMAND_INTERVAL = 2.0
REPORT_INTERVAL = 300.0


async def monitor_bmv(influx: InfluxDBManager, bmv_advertisement_key: str, counter: SharedCounter) -> None:
    # Wait for all the batteries to connect
    await counter.event.wait()

    logging.info("starting passive scan")

    bluez = BlueZScannerArgs(
        # This tells Bluez to look for advertisement packets that contain manufacturer data that
        # starts with the bytes `e1 02 10`. The first two bytes are the Victron manufacturer id,
        # in little endian and the third byte is the specific record type, Product Advertisement.
        # See:
        # https://community.victronenergy.com/storage/attachments/48745-extra-manufacturer-data-2022-12-14.pdf
        or_patterns=[OrPattern(0, AdvertisementDataType.MANUFACTURER_SPECIFIC_DATA, b"\xe1\x02\x10")]
    )

    async with BleakScanner(bluez=bluez, scanning_mode="passive") as scanner:
        # bluez enables duplicate advertising packet filtering for a passive scan, which breaks
        # our use case, since we need the data that is included in every packet. There is no way
        # to turn this off via the AdvertisementMonitor API used for a passive scan. Instead, we
        # send tell the Bluetooth adapter directly to first stop scanning and then restart scanning
        # with duplicate filtering disabled.
        # See: https://github.com/hbldh/bleak/issues/235#issuecomment-708670983
        subprocess.run(["/usr/bin/hcitool", "cmd", "0x08", "0x000C", "0x00", "0x00"], check=True)
        subprocess.run(["/usr/bin/hcitool", "cmd", "0x08", "0x000C", "0x01", "0x00"], check=True)

        async for _, advertisement_data in scanner.advertisement_data():
            victron_mfr_id = 0x02e1
            raw_data = advertisement_data.manufacturer_data.get(victron_mfr_id)

            # This check is necessary due to https://github.com/hbldh/bleak/issues/1445
            if raw_data is not None:
                parsed_data = BatteryMonitor(bmv_advertisement_key).parse(raw_data)

                await influx.write({
                    "measurement": "bmv",
                    "time": int(time.time() * 1e9),
                    "fields": {
                        "current": parsed_data.get_current(),
                        "voltage": parsed_data.get_voltage(),
                        "soc": parsed_data.get_soc(),
                        "consumed_ah": parsed_data.get_consumed_ah(),
                        "starter_voltage": parsed_data.get_starter_voltage()
                    }
                })


async def discover_batteries() -> list[UT1300]:
    """
    Scan for UT1300 Bluetooth batteries and return a list of UT1300 instances.
    """
    logging.info("starting discovery...")

    batteries = {}
    service_uuids = [uuids.normalize_uuid_16(uuid) for uuid in UT1300.DEVICE_SERVICE_UUIDS]

    async with BleakScanner(service_uuids=service_uuids) as scanner:
        async for device, advertisement_data in scanner.advertisement_data():
            device_name = advertisement_data.local_name
            if device_name is None:
                continue

            if any(name in device_name for name in UT1300.DEVICE_LOCAL_NAMES):
                logging.info("discovered %s", device_name)
                batteries[device_name] = device

            if len(batteries) == NUM_BATTERIES:
                break

    return [UT1300(name, device) for name, device in batteries.items()]


async def parse_response(battery: UT1300, influx: InfluxDBManager, _: BleakGATTCharacteristic, data: bytearray) -> None:
    """
    Ingest and parse the response data, and optionally write to InfluxDB if the data completes a message.
    """
    fields = battery.ingest_data(data)
    if fields is not None:
        await influx.write({
            "measurement": "battery",
            "tags": {"name": battery.name},
            "fields": fields,
            "time": int(time.time() * 1e9)
        })


async def monitor_and_report(battery: UT1300, influx: InfluxDBManager, counter: SharedCounter) -> None:
    """
    Connect to a UT1300 battery, set notify on a characteristic, and periodically issue commands.
    """
    logging.info("running monitoring loop...")
    characteristic = uuids.normalize_uuid_16(UT1300.CHARACTERISTIC_UUID)
    callback = partial(parse_response, battery, influx)

    async with BleakClient(battery.device) as client:
        counter.increment()

        await client.start_notify(characteristic, callback)
        while True:
            for data in UT1300.COMMANDS.values():
                await client.write_gatt_char(characteristic, data, response=False)
                await asyncio.sleep(COMMAND_INTERVAL)


async def report_successes(battery: UT1300) -> None:
    """
    Log the cumulative number of successful response parses
    """
    while True:
        await asyncio.sleep(REPORT_INTERVAL)
        battery.report_successes()


async def main():
    bmv_advertisement_key = os.environ["BMV_ADVERTISEMENT_KEY"]
    influxdb_url = os.environ["INFLUXDB_URL"]
    influxdb_token = os.environ["INFLUXDB_TOKEN"]
    influxdb_org = os.environ["INFLUXDB_ORG"]
    influxdb_bucket = os.environ["INFLUXDB_BUCKET"]

    counter = SharedCounter(NUM_BATTERIES)

    batteries = await discover_batteries()

    async with InfluxDBManager(influxdb_url, influxdb_token, influxdb_org, influxdb_bucket) as influx:
        try:
            async with asyncio.TaskGroup() as tg:
                tg.create_task(monitor_bmv(influx, bmv_advertisement_key, counter))

                for battery in batteries:
                    tg.create_task(monitor_and_report(battery, influx, counter))
                    tg.create_task(report_successes(battery))
        except asyncio.CancelledError:
            logging.info("shutting down...")

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
)

asyncio.run(main())
