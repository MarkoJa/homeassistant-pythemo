"""Import hourly Themo energy data into Home Assistant long-term statistics.

The Themo cloud reports each device's energy use per hour. The data is
imported as external statistics (``themo:energy_<device id>``), which can be
added to the Energy dashboard as individual devices.
"""

from datetime import datetime, timedelta
import logging

from pythemo.client import ThemoClient
from pythemo.models import Device
from pythemo.utils import request

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMeanType,
    StatisticMetaData,
)
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
    statistics_during_period,
)
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_conversion import EnergyConverter

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

ENERGY_UPDATE_INTERVAL = timedelta(minutes=30)

# The API only accepts a start time within the past 14 days
MAX_HISTORY = timedelta(days=13)

# A finished hour without a value is retried for this long, then counted as 0 kWh
MISSING_VALUE_GRACE = timedelta(hours=6)

MEASUREMENT_DATA = "Measurement data"
ENERGY_SERIES = "Power"  # Energy per hour in MWh, despite the name


def energy_statistic_id(device: Device) -> str:
    """Return the statistic id for a device's energy."""
    return f"{DOMAIN}:energy_{device.id}"


async def _async_get_hourly_energy(
    client: ThemoClient, device: Device, start: datetime
) -> list[tuple[datetime, float | None]]:
    """Fetch (hour start, kWh) pairs for a device from start until now."""
    data = await request(
        client._client,  # noqa: SLF001
        "get",
        f"api/environments/{device.environment_id}/devices/{device.id}/data",
        params={"from": start.strftime("%Y-%m-%dT%H:%M:%SZ")},
    )
    for block in data:
        names = [series["Name"] for series in block.get("TimeSeriesDefinitions", [])]
        if block.get("Name") != MEASUREMENT_DATA or ENERGY_SERIES not in names:
            continue
        index = names.index(ENERGY_SERIES)
        hours = []
        for point in block["TimeSeries"]:
            values = point["Values"]
            mwh = values[index] if len(values) > index else None
            hours.append(
                (
                    dt_util.utc_from_timestamp(point["Time"] / 1000),
                    None if mwh is None else mwh * 1000,
                )
            )
        return hours
    return []


async def async_import_energy(
    hass: HomeAssistant, client: ThemoClient, devices: list[Device]
) -> None:
    """Import finished hours that are not yet in the statistics."""
    now = dt_util.utcnow()
    for device in devices:
        statistic_id = energy_statistic_id(device)
        last = await get_instance(hass).async_add_executor_job(
            get_last_statistics, hass, 1, statistic_id, True, {"sum"}
        )
        if last:
            last_start = dt_util.utc_from_timestamp(last[statistic_id][0]["start"])
            total = last[statistic_id][0]["sum"] or 0.0
            start = max(last_start + timedelta(hours=1), now - MAX_HISTORY)
        else:
            last_start = None
            total = 0.0
            start = now - MAX_HISTORY
        start = start.replace(minute=0, second=0, microsecond=0)
        if start + timedelta(hours=1) > now:
            continue

        statistics = []
        for hour, kwh in await _async_get_hourly_energy(client, device, start):
            if last_start is not None and hour <= last_start:
                continue
            if hour + timedelta(hours=1) > now:
                break
            if kwh is None:
                if hour + MISSING_VALUE_GRACE > now:
                    break
                kwh = 0.0
            total += kwh
            statistics.append(StatisticData(start=hour, state=kwh, sum=total))

        if not statistics:
            continue
        _LOGGER.debug(
            "Importing %s hours of energy for %s", len(statistics), device.name
        )
        async_add_external_statistics(
            hass,
            StatisticMetaData(
                mean_type=StatisticMeanType.NONE,
                has_sum=True,
                name=f"Themo {device.name}",
                source=DOMAIN,
                statistic_id=statistic_id,
                unit_class=EnergyConverter.UNIT_CLASS,
                unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
            ),
            statistics,
        )


async def async_get_daily_energy(
    hass: HomeAssistant, devices: list[Device]
) -> dict[str, tuple[float, float]]:
    """Return (today, yesterday) kWh per device id from the imported statistics.

    Days are local days. Today only covers the hours imported so far.
    """
    today_start = dt_util.start_of_local_day()
    yesterday_start = dt_util.start_of_local_day(
        dt_util.now().date() - timedelta(days=1)
    )
    statistic_ids = {energy_statistic_id(device): device.id for device in devices}
    rows = await get_instance(hass).async_add_executor_job(
        statistics_during_period,
        hass,
        yesterday_start,
        None,
        set(statistic_ids),
        "hour",
        None,
        {"change"},
    )
    daily = {device.id: (0.0, 0.0) for device in devices}
    for statistic_id, device_id in statistic_ids.items():
        today = yesterday = 0.0
        for row in rows.get(statistic_id, []):
            change = row.get("change") or 0.0
            if row["start"] >= today_start.timestamp():
                today += change
            else:
                yesterday += change
        daily[device_id] = (round(today, 3), round(yesterday, 3))
    return daily
