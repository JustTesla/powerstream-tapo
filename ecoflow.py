import json
import asyncio
import requests
import hashlib
import hmac
import random
import time
import binascii
from tapo import ApiClient

# Функция для загрузки конфигурации
def load_config(filename="config.json"):
    with open(filename, "r") as f:
        return json.load(f)

# HMAC-SHA256 подпись
def hmac_sha256(data, key):
    hashed = hmac.new(key.encode('utf-8'), data.encode('utf-8'), hashlib.sha256).digest()
    sign = binascii.hexlify(hashed).decode('utf-8')
    return sign

# Вспомогательные функции для работы с параметрами
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

# Запросы к API
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
        print(f"get_api: {response.text}")
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
        print(f"post_api: {response.text}")
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
        print(f"put_api: {response.text}")
        return None

# Проверка, находится ли устройство онлайн
def check_if_device_is_online(SN, payload):
    for device in payload.get('data', []):
        if device.get('sn') == SN:
            return device.get('online', 0) == 1
    return False

# Функция для подключения и получения данных с устройства
async def get_power_usage(client, device_ip):
    try:
        device = await client.p110(device_ip)  # Подключение к устройству
        energy_usage = await device.get_energy_usage()  # Получение энергопотребления
        current_power = energy_usage.current_power / 1000  # Преобразуем в киловатты
        return current_power
    except Exception as e:
        print(f"Ошибка получения данных с устройства {device_ip}: {e}")
        return 0

# Функция для отправки данных на EcoFlow PowerStream
def send_to_ecoflow(key, secret, serial_number, total_power, last_power):
    print(f"send_to_ecoflow: Запрашиваем мощность {total_power} для устройства {serial_number}.")

    # Проверяем статус устройства
    url_device = "https://api.ecoflow.com/iot-open/sign/device/list"
    payload = get_api(url_device, key, secret, {"sn": serial_number})

    if not check_if_device_is_online(serial_number, payload):
        print(f"Устройство {serial_number} оффлайн. Операция отменена.")
        return last_power  # Возвращаем старое значение

    # Получаем текущую мощность
    url_quota = "https://api.ecoflow.com/iot-open/sign/device/quota"
    quotas = ["20_1.permanentWatts"]
    params = {"sn": serial_number, "params": {"quotas": quotas}}
    quota_response = post_api(url_quota, key, secret, params)

    if quota_response:
        cur_permanent_watts = round(quota_response["data"]["20_1.permanentWatts"] / 10)
        print(f"Текущая мощность на сервере EcoFlow: {cur_permanent_watts} Вт.")

        # Ограничиваем значение 0-800 Вт
        new_permanent_watts = total_power

        if new_permanent_watts > max_limit_watt:
            new_permanent_watts = max_limit_watt
        elif new_permanent_watts < 0:
            new_permanent_watts = 0

        # Отправляем только если новое значение отличается от старого
        if new_permanent_watts != cur_permanent_watts:
            # Устанавливаем новое значение мощности
            url_set = "https://api.ecoflow.com/iot-open/sign/device/quota"
            cmd_code = "WN511_SET_PERMANENT_WATTS_PACK"
            params = {"sn": serial_number, "cmdCode": cmd_code, "params": {"permanentWatts": new_permanent_watts * 10}}
            response = put_api(url_set, key, secret, params)

            if response:
                print(f"Успешно установлено новое значение: {new_permanent_watts} Вт.")
                return new_permanent_watts  # Обновляем last_power
            else:
                print(f"Ошибка при установке нового значения мощности.")
        else:
            print("Новое значение мощности не изменилось, отправка не требуется.")

    return last_power  # Возвращаем старое значение

# Функция мониторинга устройств
async def monitor_devices(devices, username, password, max_limit_watt, ecoflow_config):
    client = ApiClient(username, password)  # Создание клиента Tapo API
    last_power = 0  # Инициализация переменной для хранения последней установленной мощности

    while True:
        total_power = 0
        for device_info in devices:
            power_usage = await get_power_usage(client, device_info["ip"])
            print(f"Устройство {device_info['name']} потребляет {power_usage} Вт.")
            total_power += power_usage

        # Ограничиваем мощность до max_limit_watt
        if total_power > max_limit_watt:
            total_power = max_limit_watt

        # Отправляем данные на EcoFlow PowerStream
        last_power = send_to_ecoflow(ecoflow_config["api_key"], ecoflow_config["secret_key"], ecoflow_config["serial_number"], total_power, last_power)

        await asyncio.sleep(10)  # Пауза между запросами (можно настроить)

# Основная логика
async def main():
    config = load_config()

    username = config["tapo"]["username"]
    password = config["tapo"]["password"]
    devices = config["devices"]
    max_limit_watt = config["max_limit_watt"]
    ecoflow_config = config["ecoflow"]

    print("Запуск мониторинга устройств Tapo P115...")
    await monitor_devices(devices, username, password, max_limit_watt, ecoflow_config)

if __name__ == "__main__":
    asyncio.run(main())
