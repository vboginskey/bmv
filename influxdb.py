from typing import Any, Dict
from influxdb_client.client.influxdb_client_async import InfluxDBClientAsync


class InfluxDBManager:
    """
    Asynchrous manager for interactions with InfluxDB.
    """
    def __init__(self, url: str, token: str, org: str, bucket: str) -> None:
        self.url = url
        self.token = token
        self.org = org
        self.bucket = bucket
        self.client = None
        self.write_api = None

    async def __aenter__(self) -> 'InfluxDBManager':
        self.client = InfluxDBClientAsync(url=self.url, token=self.token, org=self.org)
        self.write_api = self.client.write_api()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.client.__aexit__(exc_type, exc_val, exc_tb)

    async def write(self, data_dict: Dict[str, Any]) -> None:
        """
        Write dictionary data to InfluxDB.
        """
        await self.write_api.write(self.bucket, self.org, data_dict)
