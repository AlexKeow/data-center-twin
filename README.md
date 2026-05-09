# Datacenter Digital Twin & Energy Simulation

## Overview

This project is a simulation-based digital twin of a data center (DC) energy system designed for machine learning, predictive analytics, and operational optimization.

The system generates realistic synthetic telemetry data for:
- IT load behavior
- GPU power consumption
- Battery energy storage system (BESS)
- Cooling infrastructure
- Temperature dynamics
- PUE (Power Usage Effectiveness)
- Failure events and anomaly scenarios
- Forecasting subsystem
- ML-ready engineered features

The generated dataset can be used for:
- Time-series forecasting
- Predictive maintenance
- Anomaly detection
- Reinforcement learning
- Energy optimization
- Digital twin development

---

# Key Features

## Energy System Simulation
- Dynamic IT load modeling
- GPU ramp-rate inertia
- Battery charging/discharging logic
- Peak load handling
- Emergency operating modes

## Cooling & Thermal Model
- Outside ambient temperature simulation
- Server room temperature dynamics
- Cooling power consumption
- PUE calculation

## Failure Simulation
Supported failure types:
- GPU failure
- Cooling failure
- Battery failure
- Grid instability
- Sensor fault

## Machine Learning Features
The dataset includes:
- Rolling statistics
- Lag features
- Forecast error metrics
- Power deficit indicators
- Temperature deviation metrics
- ML-ready prediction targets

---

# Dataset Characteristics

- 40,000 telemetry records
- 60-day simulation horizon
- Realistic time-series behavior
- Industrial-style telemetry structure
- CSV and XLSX export support

---

# ML Targets

The dataset contains supervised learning targets:
- `target_load_1h`
- `target_peak_1h`

These can be used for:
- load forecasting
- peak prediction
- predictive control systems

---

# Technologies Used

- Python
- pandas
- numpy
- synthetic telemetry generation
- time-series feature engineering

---

# File Structure

```text
generate_dataset_enhanced.py
datacenter_energy_dataset_features.csv
datacenter_energy_dataset_features.xlsx
README.md
```

---

# How to Run

Install dependencies:

```bash
pip install pandas numpy openpyxl
```

Run the generator:

```bash
python generate_dataset_enhanced.py
```

---

# Output Files

The script generates:
- `datacenter_energy_dataset_features.csv`
- `datacenter_energy_dataset_features.xlsx`

---

# Project Goal

The main goal of this project is to create a realistic industrial telemetry dataset for developing AI-driven digital twins of modern data centers.

The system focuses on:
- operational resilience
- energy efficiency
- predictive analytics
- intelligent energy management

---

# Future Improvements

Potential future extensions:
- SCADA integration
- renewable energy modeling
- real-time streaming telemetry
- reinforcement learning control
- carbon emissions optimization
- network traffic simulation
- SLA prediction

---

# Authors

Developed as part of a data center digital twin and ML analytics case study project.
