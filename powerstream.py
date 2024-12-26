import json
import asyncio
import aiohttp
import requests
import hashlib
import hmac
import random
import time
import binascii
import logging
from logging.handlers import TimedRotatingFileHandler
from datetime import datetime, timedelta
from tapo import ApiClient

# Configure logging
handler = TimedRotatingFileHandler("monitor.log", when="H", interval=1, backupCount=1)  # Логи за последний час
formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
handler.setFormatter(formatter)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[handler, logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Function to load configuration
def load_config(filename="config.json"):
    with open(filename, "r") as f:
        return json.load(f)

# HMAC-SHA256 signature
def hmac_sha256(data, key):
    hashed = hmac.new(key.encode('utf-8'), data.encode('utf-8'), hashlib.sha256).digest()
    sign = binascii.hexlify(hashed).decode('utf-8')
    return sign

# Helper functions for working with parameters
def get_map(json_obj, prefix=""):
    def flatten(obj, pre=""):
        result = {}
        if isinstance(obj, dict):
            for k, v in obj.items():
                result.update(flatten(v, f"{pre}.{k}" if pre else k))
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                result.update(flatten(item, f"{pre}[{i}]"))
        else:
            result[pre] = obj
        return result
    return flatten(json_obj, prefix)

def get_qstr(params):
    return '&'.join([f"{key}={params[key]}" for key in sorted(params.keys())])

# API requests
def get_api(url, key, secret, params=None):
    nonce = str(random.randint(100000, 999999))
    timestamp = str(int(time.time() * 1000))
    headers = {'accessKey': key, 'nonce': nonce, 'timestamp': timestamp}
    sign_str = (get_qstr(get_map(params)) + '&' if params else '') + get_qstr(headers)
    headers['sign'] = hmac_sha256(sign_str, secret)
    response = requests.get(url, headers=headers, json=params)
    if response.status_code == 200:
        return response.json()
    else:
        logger.error(f"get_api: {response.text}")
        return None

def post_api(url, key, secret, params=None):
    nonce = str(random.randint(100000, 999999))
    timestamp = str(int(time.time() * 1000))
    headers = {'accessKey': key, 'nonce': nonce, 'timestamp': timestamp}
    sign_str = (get_qstr(get_map(params)) + '&' if params else '') + get_qstr(headers)
    headers['sign'] = hmac_sha256(sign_str, secret)
    response = requests.post(url, headers=headers, json=params)
    if response.status_code == 200:
        return response.json()
    else:
        logger.error(f"post_api: {response.text}")
        return None

def put_api(url, key, secret, params=None):
    nonce = str(random.randint(100000, 999999))
    timestamp = str(int(time.time() * 1000))
    headers = {'accessKey': key, 'nonce': nonce, 'timestamp': timestamp}
    sign_str = (get_qstr(get_map(params)) + '&' if params else '') + get_qstr(headers)
    headers['sign'] = hmac_sha256(sign_str, secret)
    response = requests.put(url, headers=headers, json=params)
    if response.status_code == 200:
        return response.json()
    else:
        logger.error(f"put_api: {response.text}")
        return None

# Utility to check if time is within the restricted period
def is_night_time():
    now = datetime.now()
    if now.hour >= 18 or now.hour < 7:
        return True
    return False

# Wait until 7:00 the next day
async def wait_until_morning():
    now = datetime.now()
    if now.hour >= 18:
        next_morning = now.replace(hour=7, minute=0, second=0, microsecond=0) + timedelta(days=1)
    else:
        next_morning = now.replace(hour=7, minute=0, second=0, microsecond=0)
    sleep_time = (next_morning - now).total_seconds()
    logger.info(f"PowerStream offline after 18:00. Sleeping until 7:00 ({sleep_time / 3600:.1f} hours).")
    await asyncio.sleep(sleep_time)

# Function to check if the device is online
def check_if_device_is_online(SN, payload):
    for device in payload.get('data', []):
        if device.get('sn') == SN:
            return device.get('online', 0) == 1
    return False

# Function to connect and retrieve data from the device with timeout
async def get_power_usage(client, device_ip, timeout=5):
    try:
        device = await asyncio.wait_for(client.p110(device_ip), timeout=timeout)
        energy_usage = await asyncio.wait_for(device.get_energy_usage(), timeout=timeout)
        current_power = energy_usage.current_power / 1000
        return current_power
    except asyncio.TimeoutError:
        logger.error(f"Error: Timeout exceeded for device {device_ip}")
        return 0
    except Exception as e:
        logger.error(f"Error getting data from device {device_ip}: {e}")
        return 0

# Function to send data to EcoFlow PowerStream
def send_to_ecoflow(key, secret, serial_number, total_power, last_power):
    config = load_config()

    logger.info(f"send_to_ecoflow: Requesting power {total_power} for device {serial_number}.")

    # Check the device status
    url_device = "https://api.ecoflow.com/iot-open/sign/device/list"
    payload = get_api(url_device, key, secret, {"sn": serial_number})

    if not check_if_device_is_online(serial_number, payload):
        logger.warning(f"Device {serial_number} is offline.")
        if is_night_time():
            asyncio.run(wait_until_morning())
        return last_power

    # Get current power
    url_quota = "https://api.ecoflow.com/iot-open/sign/device/quota"
    quotas = ["20_1.permanentWatts"]
    params = {"sn": serial_number, "params": {"quotas": quotas}}
    quota_response = post_api(url_quota, key, secret, params)

    if quota_response:
        cur_permanent_watts = round(quota_response["data"]["20_1.permanentWatts"] / 10)
        logger.info(f"Current power on the EcoFlow server: {cur_permanent_watts} W.")

        # Limit the value to 0-800 W
        new_permanent_watts = total_power

        if new_permanent_watts > config["max_limit_watt"]:
            new_permanent_watts = config["max_limit_watt"]
        elif new_permanent_watts < 0:
            new_permanent_watts = 0

        if new_permanent_watts != cur_permanent_watts:
            url_set = "https://api.ecoflow.com/iot-open/sign/device/quota"
            cmd_code = "WN511_SET_PERMANENT_WATTS_PACK"
            params = {"sn": serial_number, "cmdCode": cmd_code, "params": {"permanentWatts": new_permanent_watts * 10}}
            response = put_api(url_set, key, secret, params)

            if response:
                logger.info(f"Successfully set new value: {new_permanent_watts} W.")
                return new_permanent_watts
            else:
                logger.error(f"Error setting the new power value.")
        else:
            logger.info("New power value has not changed, sending is not required.")

    return last_power

# Device monitoring function
async def monitor_devices(devices, username, password, max_limit_watt, base_consumption, ecoflow_config):
    client = ApiClient(username, password)
    last_power = 0

    while True:
        total_power = base_consumption
        for device_info in devices:
            power_usage = await get_power_usage(client, device_info["ip"], timeout=5)
            logger.info(f"Device {device_info['name']} is consuming {power_usage} W.")
            total_power += power_usage

        if total_power > max_limit_watt:
            total_power = max_limit_watt

        last_power = send_to_ecoflow(ecoflow_config["api_key"], ecoflow_config["secret_key"], ecoflow_config["serial_number"], total_power, last_power)

        await asyncio.sleep(10)

# Main logic
async def main():
    config = load_config()

    username = config["tapo"]["username"]
    password = config["tapo"]["password"]
    devices = config["devices"]
    max_limit_watt = config["max_limit_watt"]
    base_consumption = config["base_consumption"]
    ecoflow_config = config["ecoflow"]

    logger.info("Starting monitoring of Tapo P115 devices...")
    await monitor_devices(devices, username, password, max_limit_watt, base_consumption, ecoflow_config)

if __name__ == "__main__":
    asyncio.run(main())
