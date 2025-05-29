import asyncio
import sys
import os
import logging

# Nastavení loggingu
logging.basicConfig(
    level=logging.DEBUG,  # Nastavení úrovně logování na DEBUG
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Přidání loggingu pro aiohttp
logging.getLogger('aiohttp').setLevel(logging.DEBUG)

sys.path.append("custom_components\\control_my_spa")
from ControlMySpa import ControlMySpa

class Driver:
    def __init__(self):
        self.id = "driver-01"
        self.homey = self.MockHomey()

    class MockHomey:
        def __init__(self):
            self.app = self.App()

        class App:
            def log(self, message, data=None):
                print(message, data)

        def __(self, key):
            return f"Chyba: {key}"

    async def initialize_driver(self, data):
        try:
            self.config = {
                'username': data['username'],
                'password': data['password']
            }

            self.homey.app.log(f"[Driver] {self.id}")

            self._control_my_spa_client = ControlMySpa(
                self.config['username'],
                self.config['password']
            )

            await self._control_my_spa_client.init()

            self.balboa_data = await self._control_my_spa_client.getSpa()
            if not self.balboa_data:
                return False

            return True

        except Exception as error:
            print(error)
            raise Exception(self.homey.__('pair.error'))

    async def close(self):
        if hasattr(self, "_control_my_spa_client") and self._control_my_spa_client:
            await self._control_my_spa_client.close()

async def main():
    print("Start Test")

    driver = Driver()
    data = {
        'username': '',
        'password': ''
    }

    try:
        success = await driver.initialize_driver(data)
        if success:
            print("Driver inicializován.")
            print(f"teplota. {driver.balboa_data.get('currentTemp')}")
            print(".....................")
            # print(f"teplota. {driver.balboa_data}")
            print("Konec.")
        else:
            print("Driver se nepodařilo inicializovat.")
    finally:
        await driver.close()
        await asyncio.sleep(5)

if __name__ == '__main__':
    asyncio.run(main())
