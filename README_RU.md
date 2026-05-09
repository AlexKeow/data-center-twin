# Цифровой двойник энергосистемы ЦОД

## Описание проекта

Проект представляет собой симуляционную модель цифрового двойника энергосистемы дата-центра (ЦОД), предназначенную для задач машинного обучения, прогнозной аналитики и оптимизации энергопотребления.

Система генерирует реалистичный synthetic telemetry dataset, включающий:
- нагрузку ЦОД;
- потребление ГПУ;
- работу аккумуляторной системы;
- систему охлаждения;
- температурные режимы;
- PUE (Power Usage Effectiveness);
- аварийные события;
- forecasting subsystem;
- engineered ML-features.

Полученный датасет может использоваться для:
- прогнозирования нагрузки;
- anomaly detection;
- predictive maintenance;
- reinforcement learning;
- оптимизации энергосистемы;
- разработки цифрового двойника ЦОД.

---

# Основные возможности

## Симуляция энергосистемы
- динамическое моделирование нагрузки;
- инерция изменения мощности ГПУ;
- логика заряда/разряда аккумуляторов;
- обработка пиковых нагрузок;
- emergency-режимы работы.

## Система охлаждения и тепловая модель
- моделирование внешней температуры;
- температура серверной;
- энергопотребление cooling system;
- расчёт PUE.

## Моделирование аварий
Поддерживаются:
- gpu_failure;
- cooling_failure;
- battery_failure;
- grid_instability;
- sensor_fault.

## ML-признаки
Датасет включает:
- rolling statistics;
- lag features;
- forecast error metrics;
- power deficit indicators;
- температурные показатели;
- ML-ready targets.

---

# Характеристики датасета

- 40 000 телеметрических записей;
- горизонт моделирования — 60 дней;
- реалистичное поведение time-series;
- industrial telemetry structure;
- экспорт в CSV и XLSX.

---

# ML-targets

В датасете присутствуют:
- `target_load_1h`
- `target_peak_1h`

Они предназначены для:
- load forecasting;
- peak prediction;
- predictive control systems.

---

# Используемые технологии

- Python
- pandas
- numpy
- synthetic telemetry generation
- time-series feature engineering

---

# Структура проекта

```text
generate_dataset_enhanced.py
datacenter_energy_dataset_features.csv
datacenter_energy_dataset_features.xlsx
README.md
```

---

# Запуск проекта

Установка зависимостей:

```bash
pip install pandas numpy openpyxl
```

Запуск генератора:

```bash
python generate_dataset_enhanced.py
```

---

# Выходные файлы

Скрипт создаёт:
- `datacenter_energy_dataset_features.csv`
- `datacenter_energy_dataset_features.xlsx`

---

# Цель проекта

Основная цель проекта — создание реалистичного industrial telemetry dataset для разработки AI-driven цифровых двойников современных дата-центров.

Система ориентирована на:
- повышение устойчивости инфраструктуры;
- энергоэффективность;
- predictive analytics;
- интеллектуальное управление энергосистемой.

---

# Возможные улучшения

Потенциальные направления развития:
- интеграция со SCADA;
- моделирование ВИЭ;
- real-time telemetry streaming;
- reinforcement learning control;
- оптимизация углеродного следа;
- моделирование сетевого трафика;
- SLA prediction.

---

# Авторы

Проект разработан в рамках кейса по созданию цифрового двойника ЦОД и ML-аналитики.
