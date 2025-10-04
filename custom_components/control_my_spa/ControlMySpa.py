import aiohttp
import time
import asyncio
import logging
import json
import os
from . import const

_LOGGER = logging.getLogger(__name__)

class ControlMySpa:
    # BASE_URL = 'https://production.controlmyspa.net'
    BASE_URL = 'https://iot.controlmyspa.com'

    def __init__(self, email, password):
        self.email = email
        self.password = password
        self.tokenData = None
        self.userInfo = None
        self.currentSpa = None
        self.waitForResult = True
        self.scheduleFilterIntervalEnum = None
        self.spaId = None
        self.session = None
        self.createFilterScheduleIntervals()

    async def init_session(self):
        if self.session is None:
            self.session = aiohttp.ClientSession()

    async def close(self):
        if self.session:
            await self.session.close()
            self.session = None

    def getAuthHeaders(self):
        return {
            'Authorization': f"Bearer {self.tokenData['access_token']}",
            **self.getCommonHeaders()
        }

    def getCommonHeaders(self):
        return {
            'Accept': '*/*',
            'Accept-Encoding': 'gzip, deflate, br',
            'Accept-Language': 'en-GB,en;q=0.9',
            'User-Agent': 'cms/34 CFNetwork/3826.500.111.2.2 Darwin/24.4.0'
        }

    async def init(self):
        await self.init_session()
        return await self.login() and await self.getWhoAmI() 

    def isLoggedIn(self):
        if not self.tokenData:
            return False
        return self.tokenData['timestamp'] + self.tokenData['expires_in'] * 1000 > int(time.time() * 1000)

    async def login(self):
        try:
            headers = {**self.getCommonHeaders(), 'Content-Type': 'application/json'}
            payload = {'email': self.email, 'password': self.password}
            async with self.session.post(f'{self.BASE_URL}/auth/login', json=payload, headers=headers, ssl=False) as resp:
                if resp.status == 200:
                    res_json = await resp.json()
                    token = res_json.get('data', {}).get('accessToken')
                    if token:
                        self.tokenData = {
                            'access_token': token,
                            'timestamp': int(time.time() * 1000),
                            'expires_in': 3600
                        }
                        return True
                    else:
                        _LOGGER.error(f"Login Error, no login token: {res_json}")
                else:
                    _LOGGER.error(f"Login Error, HTTP status {resp.status}: {await resp.text()}")
        except Exception as e:
            _LOGGER.error(f"Login Error: {e}")
        return False

    async def getWhoAmI(self):
        try:
            headers = self.getAuthHeaders()
            async with self.session.get(f'{self.BASE_URL}/user-management/profile', headers=headers, ssl=False) as resp:
                if resp.status == 200:
                    res_json = await resp.json()
                    user = res_json.get('data', {}).get('user')
                    if user:
                        self.userInfo = user
                        _LOGGER.info(f"GetWhoAmI User exists: {user}")
                        return user
                    else:
                        _LOGGER.error(f"GetWhoAmI Unknow data: {res_json}")
                else:
                    _LOGGER.error(f"GetWhoAmI Error, HTTP status {resp.status}: {await resp.text()}")
        except Exception as e:
            _LOGGER.error(f"GetWhoAmI Error: {e}")
        return None

    async def getSpaOwner(self):
        try:
            if not self.isLoggedIn():
                await self.login()
            headers = self.getAuthHeaders()
            async with self.session.get(f'{self.BASE_URL}/spas/owned', headers=headers, ssl=False) as resp:
                if resp.status == 200:
                    res_json = await resp.json()
                    return res_json.get('data', {}).get('spas', [])
                else:
                    _LOGGER.error(f"getSpaOwner Error, HTTP status {resp.status}: {await resp.text()}")
        except Exception as e:
            _LOGGER.error(f"getSpaOwner Error: {e}")
        return None

    async def getSpa(self):
        try:
            # Test mode - načtení dat ze souboru
            if const.TEST_MODE and const.TEST_MODE.startswith("Data"):
                test_file_path = os.path.join(os.path.dirname(__file__), 'testData', f'{const.TEST_MODE}.json')
                try:
                    with open(test_file_path, 'r', encoding='utf-8') as f:
                        test_data = json.load(f)
                        _LOGGER.info(f"Načtena testovací data z {test_file_path}")
                        return self.constructCurrentState(test_data.get('data'))
                except FileNotFoundError:
                    _LOGGER.error(f"Testovací soubor nenalezen: {test_file_path}")
                    return None
                except json.JSONDecodeError as e:
                    _LOGGER.error(f"Chyba při parsování JSON souboru: {e}")
                    return None
                except Exception as e:
                    _LOGGER.error(f"Chyba při načítání testovacích dat: {e}")
                    return None
            
            # Normální režim - načtení dat z API
            if not self.isLoggedIn():
                await self.login()
            if not self.spaId:
                return None

            headers = self.getAuthHeaders()
            async with self.session.get(f'{self.BASE_URL}/spas/{self.spaId}/dashboard', headers=headers, ssl=False) as resp:
                if resp.status == 200:
                    res_json = await resp.json()
                    return self.constructCurrentState(res_json.get('data'))
                else:
                    _LOGGER.error(f"GetSpa Error, HTTP status {resp.status}: {await resp.text()}")
        except Exception as e:
            _LOGGER.error(f"GetSpa Error: {e}")
        return None

    def constructCurrentState(self, spaData):
        try:
            result = {
                'desiredTemp': float(spaData['desiredTemp']),
                'targetDesiredTemp': float(spaData['desiredTemp']),
                'currentTemp': float(spaData['currentTemp']),
                'panelLock': spaData['isPanelLocked'],
                'heaterMode': spaData['heaterMode'],
                'components': spaData.get('components', []),
                'runMode': spaData['heaterMode'],
                'tempRange': spaData['tempRange'],
                'setupParams': {
                    'highRangeLow': spaData['rangeLimits']['highRangeLow'],
                    'highRangeHigh': spaData['rangeLimits']['highRangeHigh'],
                    'lowRangeLow': spaData['rangeLimits']['lowRangeLow'],
                    'lowRangeHigh': spaData['rangeLimits']['lowRangeHigh']
                },
                'time': spaData['time'],
                # 'hour': int(spaData['time'].split(':')[0]) if spaData.get('time') else None,
                # 'minute': int(spaData['time'].split(':')[1]) if spaData.get('time') else None,
                # 'timeNotSet': not bool(spaData.get('time')),
                # 'military': spaData['isMilitaryTime'],
                'serialNumber': spaData['serialNumber'],
                'controllerSoftwareVersion': spaData['systemInfo']['controllerSoftwareVersion'],
                'isOnline': bool(spaData.get('isOnline')),
            }
            
            # Načtení TZL zones pokud je TZL připojen
            if spaData.get('primaryTZLStatus') == 'TZL_CONNECTED':
                tzl_state = spaData.get('tzlState', {})
                tzl_light_status = tzl_state.get('tzlLightStatus', {})
                tzl_configuration = tzl_state.get('tzlConfiguration', {})
                tzl_color_settings = tzl_state.get('tzlColorSettings', {})
                
                result['tzlZones'] = tzl_light_status.get('tzlZones', [])
                result['tzlZoneFunctions'] = tzl_configuration.get('tzlZoneFunctions', [])
                result['tzlColors'] = tzl_color_settings.get('tzlColors', [])
            else:
                result['tzlZones'] = []
                result['tzlZoneFunctions'] = []
                result['tzlColors'] = []
                
            return result
        except Exception as e:
            _LOGGER.error(f"constructCurrentState Error: {e}")
            return None

    async def _postAndRefresh(self, endpoint, payload):
        try:
            if not self.isLoggedIn():
                await self.login()
            headers = {**self.getAuthHeaders(), 'Content-Type': 'application/json'}
            async with self.session.post(f'{self.BASE_URL}{endpoint}', json=payload, headers=headers, ssl=False) as resp:
                if resp.status == 200:
                    await asyncio.sleep(5)
                    return await self.getSpa()
        except Exception as e:
            _LOGGER.error(f"Error in {endpoint}: {e}")
        return None

    async def setTemp(self, temp):
        return await self._postAndRefresh("/spa-commands/temperature/value", {
            "spaId": self.spaId,
            "via": "MOBILE",
            "value": temp
        })

    async def setTempRange(self, high):
        return await self._postAndRefresh("/spa-commands/temperature/range", {
            "spaId": self.spaId,
            "via": "MOBILE",
            "range": "HIGH" if high else "LOW"
        })

    async def setTime(self, date, time, military_format=True):
        return await self._postAndRefresh("/spa-commands/time   ", {
            "spaId": self.spaId,
            "via": "MOBILE",
            "date": date,
            "time": time,
            "isMilitaryFormat": military_format
    })

    async def setPanelLock(self, locked):
        return await self._postAndRefresh("/spa-commands/panel/state", {
            "spaId": self.spaId,
            "via": "MOBILE",
            "state": "LOCK_PANEL" if locked else "UNLOCK_PANEL"
        })

    async def setLightState(self, deviceNumber, desiredState):
        return await self.setComponentState(deviceNumber, desiredState, 'light')

    async def setJetState(self, deviceNumber, desiredState):
        return await self.setComponentState(deviceNumber, desiredState, 'jet')

    async def setBlowerState(self, deviceNumber, desiredState):
        return await self.setComponentState(deviceNumber, desiredState, 'blower')

    async def setComponentState(self, deviceNumber, desiredState, componentType):
        return await self._postAndRefresh("/spa-commands/component-state", {
            "deviceNumber": deviceNumber,
            "state": desiredState,
            "spaId": self.spaId,
            "via": "MOBILE",
            "componentType": componentType
        })

    async def setHeaterMode(self, mode):
        return await self._postAndRefresh("/spa-commands/temperature/heater-mode", {
            "spaId": self.spaId,
            "via": "MOBILE",
            "mode": mode
        })

    async def setFilterCycle(self, deviceNumber, numOfIntervals, time_str):
        return await self._postAndRefresh("/spa-commands/filter-cycles/schedule", {
            "spaId": self.spaId,
            "via": "MOBILE",
            "deviceNumber": deviceNumber,
            "numOfIntervals": numOfIntervals,
            "time": time_str
        })

    def createFilterScheduleIntervals(self):
        intervals = {'idisabled': 0}
        index = 1
        for hours in range(0, 25):
            for minutes in [0, 15, 30, 45]:
                if hours == 0 and minutes == 0:
                    continue
                if hours == 24 and minutes > 0:
                    continue
                label = f"i{hours}hour{'s' if hours != 1 else ''}{minutes}minutes" if minutes else f"i{hours}hour{'s' if hours != 1 else ''}"
                intervals[label] = index
                index += 1
        self.scheduleFilterIntervalEnum = intervals


