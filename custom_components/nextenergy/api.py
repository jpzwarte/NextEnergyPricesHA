"""Client for the NextEnergy customer app.

The MarketPrices page at https://mijn.nextenergy.nl/Mobile_EnergyNext/MarketPrices is an
OutSystems reactive app: its HTML is an empty shell and the prices are loaded through
JSON "screen service" calls. This client performs the same calls the app does:

1. ``ActionDoLogin`` with username/password, which sets session cookies including the
   CSRF token (``nr2Users_*`` cookie, ``crf=`` part).
2. ``ScreenDataSetGetContractByUserId`` to find the contract id.
3. ``DataActionGetPriceDataPoints`` per day and cost level, returning 24 hourly prices.

Every call must carry the module version and the action's API version. Both change
whenever NextEnergy publishes a new app version, so they are read from the app's own
JavaScript at login, with the last known values as fallback.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import logging
import re
from typing import Any
from urllib.parse import unquote

import aiohttp

_LOGGER = logging.getLogger(__name__)

HOST = "https://mijn.nextenergy.nl"
BASE_URL = f"{HOST}/Mobile_EnergyNext/"
ANONYMOUS_CSRF_TOKEN = "T6C+9iB49TLra4jEsMeSckDMNhQ="
TIMEOUT = aiohttp.ClientTimeout(total=30)


@dataclass(frozen=True)
class _Endpoint:
    script: str
    action: str
    path: str
    view: str
    fallback_api_version: str


_LOGIN = _Endpoint(
    script="Mobile_EnergyNext.EntryFlow.Login_New.mvc.js",
    action="DoLogin",
    path="screenservices/Mobile_EnergyNext/EntryFlow/Login_New/ActionDoLogin",
    view="EntryFlow.Login_New",
    fallback_api_version="6RXNTWQg6FlgienWK8L57A",
)
_CONTRACT = _Endpoint(
    script="Mobile_EnergyNext_CW.WidgetFlow.MarketPrices_Quarterly_v2.mvc.js",
    action="ScreenDataSetGetContractByUserId",
    path="screenservices/Mobile_EnergyNext_CW/WidgetFlow/MarketPrices_Quarterly_v2/ScreenDataSetGetContractByUserId",
    view="MainFlow.MarketPrices",
    fallback_api_version="8iE27Lmd9o3E3fXohOX9Uw",
)
_PRICES = _Endpoint(
    script="Mobile_EnergyNext_CW.WidgetFlow.MarketPrices_Quarterly_v2.mvc.js",
    action="DataActionGetPriceDataPoints",
    path="screenservices/Mobile_EnergyNext_CW/WidgetFlow/MarketPrices_Quarterly_v2/DataActionGetPriceDataPoints",
    view="MainFlow.MarketPrices",
    fallback_api_version="CojBpHbLdUTYB8YFvXr0TA",
)


class NextEnergyError(Exception):
    """Communication with NextEnergy failed."""


class NextEnergyAuthError(NextEnergyError):
    """The credentials were rejected."""


class _SessionError(NextEnergyError):
    """The call failed in a way a fresh login may fix."""


@dataclass(frozen=True)
class DayPrices:
    """Prices for one Dutch calendar day.

    ``electricity`` holds ``(utc_hour, price)`` tuples in chronological order; it is
    empty when the prices for that day have not been published yet.
    """

    electricity: list[tuple[int, float]]
    gas: float | None


class NextEnergyClient:
    """Talks to the NextEnergy app backend.

    The session should have its own cookie jar; the login cookies are kept there.
    """

    def __init__(self, session: aiohttp.ClientSession, username: str, password: str) -> None:
        self._session = session
        self._username = username
        self._password = password
        self._module_version: str | None = None
        self._api_versions: dict[str, str] = {}
        self._contract_id: str | None = None

    @property
    def contract_id(self) -> str | None:
        """Contract id found at login."""
        return self._contract_id

    async def login(self) -> str:
        """Log in and look up the contract. Returns the contract id."""
        self._session.cookie_jar.clear()
        await self._load_versions()
        result = await self._call(
            _LOGIN,
            {
                "inputParameters": {
                    "Username": self._username,
                    "Password": self._password,
                    "DeviceId": "",
                }
            },
        )
        if "exception" in result:
            raise NextEnergyAuthError(result["exception"].get("message", "Login failed"))
        if not self._csrf_token_from_cookie():
            raise NextEnergyAuthError("Login did not return a session")

        result = await self._call(
            _CONTRACT,
            {
                "inputParameters": {"StartIndex": 0, "MaxRecords": 1},
                "screenData": {"variables": {}},
                "clientVariables": {},
            },
        )
        try:
            self._contract_id = str(result["data"]["List"]["List"][0]["Contract"]["Id"])
        except (KeyError, IndexError, TypeError) as err:
            raise NextEnergyError(f"No contract found for this account: {result}") from err
        return self._contract_id

    async def get_day_prices(self, day: date, cost_level: str) -> DayPrices:
        """Fetch the hourly prices for ``day`` at the given cost level."""
        if self._contract_id is None:
            await self.login()
        try:
            return await self._fetch_day_prices(day, cost_level)
        except _SessionError as err:
            _LOGGER.debug("Price call failed (%s), logging in again", err)
            await self.login()
            return await self._fetch_day_prices(day, cost_level)

    async def _fetch_day_prices(self, day: date, cost_level: str) -> DayPrices:
        result = await self._call(
            _PRICES,
            {
                "screenData": {
                    "variables": {
                        "ContractId": self._contract_id,
                        "DateTime": f"{day.isoformat()}T00:00:00.000Z",
                    }
                },
                "clientVariables": {
                    "PriceDate": day.isoformat(),
                    "PriceCostLevel": cost_level,
                },
            },
        )
        if "exception" in result:
            # An expired session surfaces as a server-side NullReferenceException.
            raise _SessionError(result["exception"].get("message"))
        data = result.get("data") or {}
        points = [
            (int(point["Label"]), float(point["Value"]))
            for point in (data.get("DataPoints") or {}).get("List", [])
            if point.get("SeriesName") == "Electricity"
        ]
        gas = float(data["CurrentGasPrice"]) if data.get("HasGasPrice") else None
        return DayPrices(electricity=points, gas=gas)

    async def _call(self, endpoint: _Endpoint, body: dict[str, Any], retry: bool = True) -> dict[str, Any]:
        payload = {
            "versionInfo": {
                "moduleVersion": self._module_version,
                "apiVersion": self._api_versions.get(endpoint.action, endpoint.fallback_api_version),
            },
            "viewName": endpoint.view,
            **body,
        }
        headers = {
            "Content-Type": "application/json; charset=UTF-8",
            "Accept": "application/json",
            "X-CSRFToken": self._csrf_token_from_cookie() or ANONYMOUS_CSRF_TOKEN,
        }
        try:
            async with self._session.post(
                BASE_URL + endpoint.path, json=payload, headers=headers, timeout=TIMEOUT
            ) as resp:
                if resp.status in (401, 403):
                    raise _SessionError(f"HTTP {resp.status}")
                if resp.status != 200:
                    raise NextEnergyError(f"{endpoint.action}: HTTP {resp.status}")
                result = await resp.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError) as err:
            raise NextEnergyError(f"{endpoint.action}: {err}") from err

        version_info = result.get("versionInfo") or {}
        if version_info.get("hasModuleVersionChanged") or version_info.get("hasApiVersionChanged"):
            if not retry:
                raise NextEnergyError(f"{endpoint.action}: app version changed and could not be resolved")
            _LOGGER.debug("NextEnergy app was updated, reloading versions")
            await self._load_versions()
            return await self._call(endpoint, body, retry=False)
        return result

    async def _load_versions(self) -> None:
        """Read the current module version and action API versions from the app."""
        module_info = await self._get_json(BASE_URL + "moduleservices/moduleinfo")
        manifest = module_info["manifest"]
        self._module_version = manifest["versionToken"]
        url_versions: dict[str, str] = manifest.get("urlVersions", {})

        scripts: dict[str, str] = {}
        for endpoint in (_LOGIN, _CONTRACT, _PRICES):
            key = f"/Mobile_EnergyNext/scripts/{endpoint.script}"
            if key not in scripts:
                try:
                    scripts[key] = await self._get_text(HOST + key + url_versions.get(key, ""))
                except NextEnergyError as err:
                    _LOGGER.debug("Could not load %s: %s", key, err)
                    scripts[key] = ""
            match = re.search(
                rf'"{endpoint.action}", "{re.escape(endpoint.path)}", "([\w-]+)"', scripts[key]
            )
            if match:
                self._api_versions[endpoint.action] = match.group(1)
            else:
                _LOGGER.warning(
                    "Could not find the API version of %s; using the last known value",
                    endpoint.action,
                )

    def _csrf_token_from_cookie(self) -> str | None:
        for cookie in self._session.cookie_jar:
            if cookie.key.startswith("nr2Users"):
                for part in unquote(cookie.value).split(";"):
                    if part.startswith("crf="):
                        return part[4:]
        return None

    async def _get_json(self, url: str) -> dict[str, Any]:
        try:
            async with self._session.get(url, timeout=TIMEOUT) as resp:
                resp.raise_for_status()
                return await resp.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError) as err:
            raise NextEnergyError(f"{url}: {err}") from err

    async def _get_text(self, url: str) -> str:
        try:
            async with self._session.get(url, timeout=TIMEOUT) as resp:
                resp.raise_for_status()
                return await resp.text()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise NextEnergyError(f"{url}: {err}") from err
