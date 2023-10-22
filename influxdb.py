from influxdb_client.client.influxdb_client_async import InfluxDBClientAsync
import logging

class InfluxDBManager:
    def __init__(self, url, token, org, bucket):
        self.url = url
        self.token = token
        self.org = org
        self.bucket = bucket
        self.client = None
        self.write_api = None

    async def __aenter__(self):
        self.client = InfluxDBClientAsync(url=self.url, token=self.token, org=self.org)
        self.write_api = self.client.write_api()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        logging.info("Closing InfluxDBManager")
        await self.client.__aexit__(exc_type, exc_val, exc_tb)

    async def write(self, data_dict):
        await self.write_api.write(self.bucket, self.org, data_dict)
