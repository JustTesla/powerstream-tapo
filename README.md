# Tapo P115 Monitor to EcoFlow PowerStream Integration

This service monitors Tapo P115 smart plugs and sends real-time energy consumption data to the EcoFlow PowerStream system. Based on the current power consumption from the smart plugs, the service dynamically adjusts the base load of the EcoFlow PowerStream, optimizing energy usage.

## Features

- **Real-time Monitoring**: Constantly monitors the energy consumption from multiple Tapo P115 smart plugs.
- **Dynamic Base Load Adjustment**: Sends consumption data to EcoFlow PowerStream for automatic adjustment of the base load, optimizing energy efficiency.
- **Seamless Integration**: Communicates with the EcoFlow PowerStream API for smooth energy management.
- **Scalability**: Supports multiple Tapo P115 smart plugs for comprehensive household or office energy monitoring.

## How It Works

1. **Data Collection**: The service continuously retrieves power consumption data from Tapo P115 smart plugs.
2. **Processing**: The data is processed to calculate the current energy usage.
3. **Transmission**: The calculated load data is sent to the EcoFlow PowerStream system.
4. **Dynamic Load Management**: Based on the data received, EcoFlow PowerStream adjusts the base load dynamically to optimize energy distribution.

## Prerequisites

- **Tapo P115 Smart Plugs**: The service requires access to your Tapo P115 devices.
- **EcoFlow PowerStream System**: The service communicates with an EcoFlow PowerStream setup.
- **API Access**: You will need access to both Tapo's local API for monitoring and EcoFlow's API for controlling the PowerStream load.
- **Remove old library**: pip remove pyp100
- **Install another library**: pip install git+https://github.com/almottier/TapoP100.git@main

