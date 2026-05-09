import os
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import warnings

from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import numbers as xl_numbers

warnings.filterwarnings('ignore')

# ============================================================
# КОНФИГУРАЦИЯ
# ============================================================
CONFIG = {
    # 60 дней, 40 000 строк
    'n_rows': 40_000,
    'simulation_days': 60,
    'start_time': datetime(2024, 1, 1, 0, 0, 0),

    # Шаг времени будет вычислен автоматически под 60 дней / 40 000 строк
    'time_step_minutes': None,

    # ГОРИЗОНТ ДЛЯ ML-TARGET
    'forecast_horizon_minutes': 60,

    # Нагрузка ЦОД
    'base_load_MW': 20.0,
    'load_min_MW': 5.0,
    'load_max_MW': 50.0,
    'daily_amplitude_MW': 8.0,
    'weekly_amplitude_MW': 3.0,

    # Пики нагрузки
    'spike_probability': 0.012,
    'spike_magnitude_MW': (8, 20),
    'spike_duration_steps': (3, 15),

    # ГПУ
    'gpu_max_power_MW': 50.0,
    'gpu_min_power_MW': 8.0,
    'gpu_ramp_rate_MW_per_step': 0.8,
    'gpu_efficiency_noise': 0.02,

    # Аккумулятор
    'battery_capacity_MWh': 30.0,
    'battery_max_output_MW': 15.0,
    'battery_max_charge_rate_MW': 8.0,
    'battery_initial_charge_pct': 50.0,
    'battery_target_charge_pct': 43.0,
    'battery_min_charge_pct': 30.0,
    'battery_max_charge_pct': 95.0,

    # Охлаждение и температура
    'ambient_temp_base_C': 2.0,
    'ambient_daily_amplitude_C': 5.0,
    'server_room_target_temp_C': 24.0,
    'cooling_base_MW': 1.4,
    'cooling_load_factor': 0.085,
    'cooling_temp_factor': 0.14,
    'cooling_ambient_factor': 0.06,
    'server_temp_inertia': 0.20,

    # Аварыи / инциденты
    'failure_probability': 0.003,
    'failure_duration_steps': (6, 30),
    'gpu_failure_degradation': (0.3, 0.7),
    'cooling_failure_efficiency': (0.55, 0.85),
    'battery_failure_capacity': (0.5, 0.8),

    # Шум
    'load_noise_std': 0.5,
    'gpu_noise_std': 0.15,
    'battery_noise_std': 0.05,
    'forecast_noise_std': 1.5,
    'ambient_noise_std': 0.9,
    'server_temp_noise_std': 0.35,

    # Прогноз
    'forecast_bias': 0.3,
    'auxiliary_power_MW': 0.8,
}

# Автоматический пересчет шага и горизонта
CONFIG['time_step_minutes'] = (CONFIG['simulation_days'] * 24 * 60) / CONFIG['n_rows']
CONFIG['forecast_horizon_steps'] = max(
    1,
    int(round(CONFIG['forecast_horizon_minutes'] / CONFIG['time_step_minutes']))
)

np.random.seed(42)


# ============================================================
# ГЕНЕРАЦИЯ БАЗОВОЙ НАГРУЗКИ
# ============================================================
def generate_base_load(n, cfg):
    """Генерация базовой нагрузки с суточными и недельными циклами"""
    t = np.arange(n)
    step_hours = cfg['time_step_minutes'] / 60.0

    hours = (t * step_hours) % 24
    daily = cfg['daily_amplitude_MW'] * (
        -np.cos(2 * np.pi * (hours - 15) / 24)
        + 0.3 * np.sin(4 * np.pi * hours / 24)
    )

    days = (t * step_hours / 24) % 7
    weekly = cfg['weekly_amplitude_MW'] * np.where(
        (days >= 5), -1.0, 0.3 * np.sin(2 * np.pi * days / 5)
    )

    trend = 2.0 * t / n

    random_walk = np.cumsum(np.random.normal(0, 0.05, n))
    random_walk = random_walk - np.linspace(random_walk[0], random_walk[-1], n)

    base = cfg['base_load_MW'] + daily + weekly + trend + random_walk
    return base


def generate_spikes(n, cfg):
    """Генерация случайных пиков нагрузки"""
    spikes = np.zeros(n)
    i = 0
    spike_events = []

    while i < n:
        if np.random.random() < cfg['spike_probability']:
            magnitude = np.random.uniform(*cfg['spike_magnitude_MW'])
            duration = np.random.randint(*cfg['spike_duration_steps'])

            rise_steps = max(1, duration // 4)
            fall_steps = duration - rise_steps

            for j in range(rise_steps):
                idx = i + j
                if idx < n:
                    spikes[idx] += magnitude * ((j + 1) / rise_steps)

            for j in range(fall_steps):
                idx = i + rise_steps + j
                if idx < n:
                    spikes[idx] += magnitude * (1 - j / fall_steps)

            spike_events.append({
                'start': i,
                'duration': duration,
                'magnitude': magnitude,
            })
            i += duration + np.random.randint(5, 20)
        else:
            i += 1

    return spikes, spike_events


def generate_ambient_temperature(n, cfg):
    """Наружная температура с суточным циклом и шумом"""
    t = np.arange(n)
    step_hours = cfg['time_step_minutes'] / 60.0
    hours = (t * step_hours) % 24
    days = t * step_hours / 24

    daily = cfg['ambient_daily_amplitude_C'] * np.sin(2 * np.pi * (hours - 15) / 24)
    trend = 0.4 * np.sin(2 * np.pi * days / 60)
    noise = np.random.normal(0, cfg['ambient_noise_std'], n)

    ambient = cfg['ambient_temp_base_C'] + daily + trend + noise
    return ambient


# ============================================================
# АВАРИИ / ИНЦИДЕНТЫ
# ============================================================
def generate_failures(n, cfg, load_MW, ambient_temp):
    """Генерация аварийных событий с типами отказов"""
    failure_flag = np.zeros(n, dtype=int)
    failure_type = np.array(['normal'] * n, dtype=object)

    gpu_degradation = np.ones(n)
    cooling_efficiency = np.ones(n)
    battery_availability = np.ones(n)
    sensor_fault = np.zeros(n, dtype=int)

    failure_events = []
    i = 0

    # Вероятности типов инцидентов
    failure_types = [
        'gpu_failure',
        'cooling_failure',
        'battery_failure',
        'grid_instability',
        'sensor_fault',
    ]
    base_weights = np.array([0.34, 0.24, 0.16, 0.18, 0.08], dtype=float)

    while i < n:
        load_stress = np.clip((load_MW[i] - cfg['base_load_MW']) / 25.0, 0, 1)
        temp_stress = np.clip((ambient_temp[i] + 10) / 35.0, 0, 1)
        stress = 0.55 * load_stress + 0.45 * temp_stress

        failure_prob = cfg['failure_probability'] * (1.0 + 1.8 * stress)

        if np.random.random() < failure_prob:
            duration = np.random.randint(*cfg['failure_duration_steps'])
            event_type = np.random.choice(
                failure_types,
                p=(base_weights / base_weights.sum())
            )

            for j in range(duration):
                idx = i + j
                if idx >= n:
                    break

                failure_flag[idx] = 1
                failure_type[idx] = event_type

                if event_type == 'gpu_failure':
                    degradation = np.random.uniform(*cfg['gpu_failure_degradation'])
                    if j < duration * 0.35:
                        gpu_degradation[idx] = degradation
                    else:
                        recovery = (j - duration * 0.35) / max(1e-9, duration * 0.65)
                        gpu_degradation[idx] = degradation + (1 - degradation) * recovery * 0.6

                elif event_type == 'cooling_failure':
                    efficiency = np.random.uniform(*cfg['cooling_failure_efficiency'])
                    if j < duration * 0.4:
                        cooling_efficiency[idx] = efficiency
                    else:
                        recovery = (j - duration * 0.4) / max(1e-9, duration * 0.6)
                        cooling_efficiency[idx] = efficiency + (1 - efficiency) * recovery * 0.5

                elif event_type == 'battery_failure':
                    availability = np.random.uniform(*cfg['battery_failure_capacity'])
                    if j < duration * 0.5:
                        battery_availability[idx] = availability
                    else:
                        recovery = (j - duration * 0.5) / max(1e-9, duration * 0.5)
                        battery_availability[idx] = availability + (1 - availability) * recovery * 0.5

                elif event_type == 'grid_instability':
                    # Для сетевой нестабильности физическая деградация слабее, но режим аварийный
                    gpu_degradation[idx] = 1.0
                    cooling_efficiency[idx] = 1.0
                    battery_availability[idx] = 1.0

                elif event_type == 'sensor_fault':
                    sensor_fault[idx] = 1

            failure_events.append({
                'start': i,
                'duration': duration,
                'type': event_type,
            })

            # После аварии/инцидента делаем паузу
            i += duration + np.random.randint(50, 200)
        else:
            i += 1

    return {
        'failure_flag': failure_flag,
        'failure_type': failure_type,
        'gpu_degradation': gpu_degradation,
        'cooling_efficiency': cooling_efficiency,
        'battery_availability': battery_availability,
        'sensor_fault': sensor_fault,
        'failure_events': failure_events,
    }


# ============================================================
# СИМУЛЯЦИЯ ЭНЕРГОСИСТЕМЫ
# ============================================================
def simulate_energy_system(n, cfg):
    """Основная симуляция с физической моделью"""

    # 1. Генерация нагрузки и окружающей среды
    base_load = generate_base_load(n, cfg)
    spikes, spike_events = generate_spikes(n, cfg)
    ambient_temp = generate_ambient_temperature(n, cfg)
    load_noise = np.random.normal(0, cfg['load_noise_std'], n)

    load_raw = base_load + spikes + load_noise
    load_MW = np.clip(load_raw, cfg['load_min_MW'], cfg['load_max_MW'])

    # 2. Генерация аварий
    failures = generate_failures(n, cfg, load_MW, ambient_temp)

    # 3. Прогноз нагрузки
    forecast_load = np.roll(load_MW, -cfg['forecast_horizon_steps'])
    forecast_load[-cfg['forecast_horizon_steps']:] = load_MW[-cfg['forecast_horizon_steps']:]
    forecast_noise = np.random.normal(cfg['forecast_bias'], cfg['forecast_noise_std'], n)
    forecast_load = forecast_load + forecast_noise
    forecast_load = np.clip(forecast_load, cfg['load_min_MW'], cfg['load_max_MW'])

    # 4. Симуляция ГПУ / батареи / охлаждения
    gpu_power = np.zeros(n)
    battery_charge = np.zeros(n)
    battery_output = np.zeros(n)
    cooling_power = np.zeros(n)
    server_room_temp = np.zeros(n)
    pue = np.zeros(n)
    mode = ['normal'] * n

    # Начальные условия
    gpu_power[0] = load_MW[0] * 0.9
    battery_charge[0] = cfg['battery_initial_charge_pct']
    server_room_temp[0] = cfg['server_room_target_temp_C'] + 0.5

    step_hours = cfg['time_step_minutes'] / 60.0
    target_soc = cfg['battery_target_charge_pct']

    for i in range(1, n):
        hour = ((i * cfg['time_step_minutes']) / 60.0) % 24

        # --- ГПУ ---
        target_gpu = load_MW[i]
        max_available_gpu = cfg['gpu_max_power_MW'] * failures['gpu_degradation'][i]

        gpu_delta = target_gpu - gpu_power[i - 1]
        max_ramp = cfg['gpu_ramp_rate_MW_per_step']

        if gpu_delta > max_ramp:
            gpu_delta = max_ramp
        elif gpu_delta < -max_ramp * 1.5:
            gpu_delta = -max_ramp * 1.5

        gpu_power_raw = gpu_power[i - 1] + gpu_delta
        gpu_power_raw = np.clip(gpu_power_raw, cfg['gpu_min_power_MW'], max_available_gpu)

        gpu_power[i] = gpu_power_raw + np.random.normal(0, cfg['gpu_noise_std'])
        gpu_power[i] = np.clip(gpu_power[i], cfg['gpu_min_power_MW'], max_available_gpu)

        # --- Охлаждение и температура ---
        cooling_cap_penalty = failures['cooling_efficiency'][i]
        current_temp = server_room_temp[i - 1]

        cooling_base = (
            cfg['cooling_base_MW']
            + cfg['cooling_load_factor'] * load_MW[i]
            + cfg['cooling_ambient_factor'] * max(0.0, ambient_temp[i] - 5.0)
            + cfg['cooling_temp_factor'] * max(0.0, current_temp - cfg['server_room_target_temp_C'])
        )
        cooling_power_raw = cooling_base / max(0.4, cooling_cap_penalty)
        cooling_power[i] = max(
            0.0,
            cooling_power_raw + np.random.normal(0, 0.08)
        )

        # Температура серверной
        heat_from_it = 0.10 * load_MW[i] + 0.06 * gpu_power[i]
        cooling_effect = 0.55 * cooling_power[i] * cooling_cap_penalty
        external_pull = 0.10 * (ambient_temp[i] - current_temp)

        temp_delta = (
            0.02 * heat_from_it
            - 0.03 * cooling_effect
            + external_pull
        )
        if failures['failure_type'][i] == 'cooling_failure':
            temp_delta += 0.8
        elif failures['failure_type'][i] == 'grid_instability':
            temp_delta += 0.25

        server_room_temp[i] = current_temp + cfg['server_temp_inertia'] * temp_delta + np.random.normal(0, cfg['server_temp_noise_std'])
        server_room_temp[i] = np.clip(server_room_temp[i], 18.0, 45.0)

        # --- Дефицит / избыток мощности ---
        deficit = load_MW[i] - gpu_power[i]

        current_charge_MWh = battery_charge[i - 1] / 100.0 * cfg['battery_capacity_MWh']
        battery_available_factor = failures['battery_availability'][i]

        if deficit > 0:
            max_discharge = min(
                cfg['battery_max_output_MW'] * battery_available_factor,
                current_charge_MWh / step_hours,
                deficit * 1.15
            )

            # Поддерживаем батарею вокруг целевого SOC
            if battery_charge[i - 1] < target_soc:
                soc_guard = 0.35
            elif battery_charge[i - 1] < target_soc + 7:
                soc_guard = 0.55
            else:
                soc_guard = 1.00

            if failures['failure_type'][i] in ('gpu_failure', 'grid_instability', 'cooling_failure'):
                battery_out = min(max_discharge, deficit * 1.15)
            else:
                battery_out = min(max_discharge, deficit * soc_guard)

            battery_out = max(0.0, battery_out)
            energy_out_MWh = battery_out * step_hours
            new_charge_MWh = current_charge_MWh - energy_out_MWh
            battery_output[i] = battery_out + np.random.normal(0, cfg['battery_noise_std'])
            battery_output[i] = max(0.0, battery_output[i])

        else:
            max_charge_space = (
                cfg['battery_max_charge_pct'] / 100.0 * cfg['battery_capacity_MWh']
                - current_charge_MWh
            )

            off_peak = (hour < 6) or (hour >= 22)
            extra_charge_need = max(
                0.0,
                (target_soc - battery_charge[i - 1]) / 100.0 * cfg['battery_capacity_MWh'] / step_hours
            )

            charge_rate = min(
                cfg['battery_max_charge_rate_MW'] * battery_available_factor,
                abs(deficit) * 0.9 + (extra_charge_need * 0.85 if off_peak else 0.0),
                max_charge_space / step_hours
            )
            charge_rate = max(0.0, charge_rate)

            energy_in_MWh = charge_rate * step_hours
            new_charge_MWh = current_charge_MWh + energy_in_MWh
            battery_output[i] = 0.0

            # Дополнительно подзаряжаем от сети ночью, чтобы SOC держался около 41%
            if battery_charge[i - 1] < target_soc and off_peak and failures['failure_type'][i] != 'battery_failure':
                grid_top_up = min(
                    extra_charge_need * 0.60,
                    max_charge_space / step_hours - charge_rate
                )
                if grid_top_up > 0:
                    new_charge_MWh += grid_top_up * step_hours

        new_charge_pct = (new_charge_MWh / cfg['battery_capacity_MWh']) * 100.0
        battery_charge[i] = np.clip(
            new_charge_pct,
            cfg['battery_min_charge_pct'],
            cfg['battery_max_charge_pct']
        )

        # --- PUE ---
        total_power = gpu_power[i] + cooling_power[i] + cfg['auxiliary_power_MW']
        pue[i] = total_power / max(gpu_power[i], 1.0)

        # --- Определение режима ---
        if failures['failure_flag'][i]:
            if failures['failure_type'][i] in ('gpu_failure', 'cooling_failure', 'grid_instability'):
                mode[i] = 'emergency'
            else:
                mode[i] = 'peak'
        elif deficit > 5.0 or load_MW[i] > cfg['base_load_MW'] + cfg['daily_amplitude_MW'] + 5:
            mode[i] = 'peak'
        else:
            mode[i] = 'normal'

    # Начальные значения для pue и cooling
    pue[0] = (gpu_power[0] + cooling_power[0] + cfg['auxiliary_power_MW']) / max(gpu_power[0], 1.0)
    cooling_power[0] = cooling_power[1] if n > 1 else cfg['cooling_base_MW']

    return {
        'load_MW': load_MW,
        'gpu_power': gpu_power,
        'battery_charge': battery_charge,
        'battery_output': battery_output,
        'forecast_load': forecast_load,
        'mode': mode,
        'failure': failures['failure_flag'],
        'failure_type': failures['failure_type'],
        'outside_temp_C': ambient_temp,
        'server_room_temp_C': server_room_temp,
        'cooling_power_MW': cooling_power,
        'pue': pue,
        'gpu_degradation': failures['gpu_degradation'],
        'cooling_efficiency': failures['cooling_efficiency'],
        'battery_availability': failures['battery_availability'],
        'sensor_fault': failures['sensor_fault'],
    }


# ============================================================
# СБОРКА ДАТАСЕТА
# ============================================================
def build_dataset(cfg):
    n = cfg['n_rows']

    print(f"Генерация {n} записей...")
    print(f"Период: {n * cfg['time_step_minutes'] / 60 / 24:.1f} дней")
    print(f"Шаг времени: {cfg['time_step_minutes']:.3f} минуты")
    print(f"Горизонт ML-target: {cfg['forecast_horizon_steps']} шагов (~{cfg['forecast_horizon_minutes']} минут)")

    timestamps = [
        cfg['start_time'] + timedelta(minutes=i * cfg['time_step_minutes'])
        for i in range(n)
    ]

    data = simulate_energy_system(n, cfg)

    df = pd.DataFrame({
        'timestamp': timestamps,
        'load_MW': np.round(data['load_MW'], 3),
        'gpu_power': np.round(data['gpu_power'], 3),
        'battery_charge': np.round(data['battery_charge'], 2),
        'battery_output': np.round(data['battery_output'], 3),
        'forecast_load': np.round(data['forecast_load'], 3),
        'outside_temp_C': np.round(data['outside_temp_C'], 2),
        'server_room_temp_C': np.round(data['server_room_temp_C'], 2),
        'cooling_power_MW': np.round(data['cooling_power_MW'], 3),
        'pue': np.round(data['pue'], 3),
        'mode': data['mode'],
        'failure': data['failure'],
        'failure_type': data['failure_type'],
    })

    return df


# ============================================================
# ДОБАВЛЕНИЕ ИНЖЕНЕРНЫХ ПРИЗНАКОВ
# ============================================================
def add_engineered_features(df, cfg):
    """Добавляет полезные признаки для ML"""
    df = df.copy()

    # Временные признаки
    df['hour'] = df['timestamp'].dt.hour
    df['day_of_week'] = df['timestamp'].dt.dayofweek
    df['is_weekend'] = (df['day_of_week'] >= 5).astype(int)

    # Скользящие статистики
    df['load_rolling_mean_12'] = df['load_MW'].rolling(12, min_periods=1).mean()
    df['load_rolling_std_12'] = df['load_MW'].rolling(12, min_periods=1).std().fillna(0)
    df['load_rolling_max_12'] = df['load_MW'].rolling(12, min_periods=1).max()

    # Температурные признаки
    df['ambient_rolling_mean_12'] = df['outside_temp_C'].rolling(12, min_periods=1).mean()
    df['server_temp_rolling_mean_12'] = df['server_room_temp_C'].rolling(12, min_periods=1).mean()

    # Дельты
    df['load_delta'] = df['load_MW'].diff().fillna(0)
    df['gpu_delta'] = df['gpu_power'].diff().fillna(0)
    df['battery_charge_delta'] = df['battery_charge'].diff().fillna(0)
    df['server_temp_delta'] = df['server_room_temp_C'].diff().fillna(0)
    df['pue_delta'] = df['pue'].diff().fillna(0)

    # Дефицит мощности
    df['power_deficit'] = df['load_MW'] - df['gpu_power']

    # Отношение нагрузки к мощности ГПУ
    df['load_to_gpu_ratio'] = df['load_MW'] / df['gpu_power'].clip(lower=1.0)

    # Ошибка прогноза
    df['forecast_error'] = df['forecast_load'] - df['load_MW']

    # Эффективность охлаждения
    df['temp_delta_vs_target'] = df['server_room_temp_C'] - cfg['server_room_target_temp_C']
    df['cooling_efficiency_proxy'] = df['cooling_power_MW'] / df['load_MW'].clip(lower=1.0)

    # Лаговые признаки
    for lag in [1, 3, 6, 12]:
        df[f'load_lag_{lag}'] = df['load_MW'].shift(lag).bfill()
        df[f'pue_lag_{lag}'] = df['pue'].shift(lag).bfill()

    # ML-ready target: нагрузка через 1 час
    horizon = cfg['forecast_horizon_steps']
    df['target_load_1h'] = df['load_MW'].shift(-horizon)

    # Дополнительный бинарный target для классификации
    peak_threshold = cfg['base_load_MW'] + cfg['daily_amplitude_MW'] + 5
    df['target_peak_1h'] = (df['target_load_1h'] > peak_threshold).astype('float')

    return df


# ============================================================
# ВАЛИДАЦИЯ
# ============================================================
def validate_dataset(df, cfg):
    print("\n" + "=" * 60)
    print("ВАЛИДАЦИЯ ДАТАСЕТА")
    print("=" * 60)

    print(f"\nРазмер: {len(df)} строк, {len(df.columns)} столбцов")
    print(f"Период: {df['timestamp'].min()} — {df['timestamp'].max()}")

    print(f"\n--- Нагрузка (load_MW) ---")
    print(f"  Мин: {df['load_MW'].min():.2f} МВт")
    print(f"  Макс: {df['load_MW'].max():.2f} МВт")
    print(f"  Среднее: {df['load_MW'].mean():.2f} МВт")
    print(f"  Стд: {df['load_MW'].std():.2f} МВт")

    print(f"\n--- ГПУ (gpu_power) ---")
    print(f"  Мин: {df['gpu_power'].min():.2f} МВт")
    print(f"  Макс: {df['gpu_power'].max():.2f} МВт")
    print(f"  Среднее: {df['gpu_power'].mean():.2f} МВт")

    print(f"\n--- Охлаждение и температура ---")
    print(f"  Outside temp: {df['outside_temp_C'].min():.1f} — {df['outside_temp_C'].max():.1f} °C")
    print(f"  Server temp: {df['server_room_temp_C'].min():.1f} — {df['server_room_temp_C'].max():.1f} °C")
    print(f"  Cooling power avg: {df['cooling_power_MW'].mean():.2f} МВт")
    print(f"  PUE avg: {df['pue'].mean():.3f}")

    print(f"\n--- Аккумулятор ---")
    print(f"  Заряд: {df['battery_charge'].min():.1f}% — {df['battery_charge'].max():.1f}%")
    print(f"  Средний заряд: {df['battery_charge'].mean():.1f}%")
    print(f"  Макс выход: {df['battery_output'].max():.2f} МВт")

    print(f"\n--- Режимы ---")
    mode_counts = df['mode'].value_counts()
    for m, c in mode_counts.items():
        print(f"  {m}: {c} ({c/len(df)*100:.1f}%)")

    print(f"\n--- Типы аварий ---")
    failure_types = df.loc[df['failure'] == 1, 'failure_type'].value_counts()
    for ft, c in failure_types.items():
        print(f"  {ft}: {c}")
    print(f"  Аварийных шагов: {df['failure'].sum()} ({df['failure'].mean()*100:.2f}%)")

    print(f"\n--- Корреляции ---")
    numeric_cols = ['load_MW', 'gpu_power', 'battery_charge', 'battery_output',
                    'forecast_load', 'outside_temp_C', 'server_room_temp_C',
                    'cooling_power_MW', 'pue']
    corr = df[numeric_cols].corr(numeric_only=True)
    print(f"  load_MW ↔ gpu_power: {corr.loc['load_MW', 'gpu_power']:.3f}")
    print(f"  load_MW ↔ forecast_load: {corr.loc['load_MW', 'forecast_load']:.3f}")
    print(f"  load_MW ↔ pue: {corr.loc['load_MW', 'pue']:.3f}")
    print(f"  server_room_temp_C ↔ cooling_power_MW: {corr.loc['server_room_temp_C', 'cooling_power_MW']:.3f}")

    print(f"\n--- Инерция ГПУ ---")
    gpu_diff = df['gpu_power'].diff().abs()
    print(f"  Макс изменение за шаг: {gpu_diff.max():.3f} МВт")
    print(f"  Среднее изменение: {gpu_diff.mean():.3f} МВт")
    print(f"  95-й перцентиль: {gpu_diff.quantile(0.95):.3f} МВт")

    print(f"\n--- Реакция батареи на пики ---")
    peak_mask = df['mode'] == 'peak'
    normal_mask = df['mode'] == 'normal'
    print(f"  Средний выход (normal): {df.loc[normal_mask, 'battery_output'].mean():.3f} МВт")
    print(f"  Средний выход (peak): {df.loc[peak_mask, 'battery_output'].mean():.3f} МВт")
    if (df['mode'] == 'emergency').any():
        emerg_mask = df['mode'] == 'emergency'
        print(f"  Средний выход (emergency): {df.loc[emerg_mask, 'battery_output'].mean():.3f} МВт")

    target_mean = df['battery_charge'].mean()
    print(f"\n--- SOC батареи ---")
    print(f"  Целевой SOC: {cfg['battery_target_charge_pct']}%")
    print(f"  Фактический средний SOC: {target_mean:.1f}%")

    print("\n✅ Валидация завершена")


# ============================================================
# СОХРАНЕНИЕ В XLSX С ПРАВИЛЬНОЙ ТИПИЗАЦИЕЙ
# ============================================================
def save_xlsx_typed(df: pd.DataFrame, path: str) -> None:
    """
    Записывает DataFrame в .xlsx через openpyxl, форсируя:
    - числа -> числовые ячейки (а не текст);
    - timestamp -> datetime-ячейки с явным форматом;
    - строковые object-колонки (mode, failure_type) -> текст,
      чтобы Excel не пытался распарсить их как даты;
    - NaN -> пустая ячейка.
    """
    wb = Workbook(write_only=True)
    ws = wb.create_sheet(title="telemetry")

    # Классификация колонок
    datetime_cols = set(df.select_dtypes(include=['datetime64[ns]']).columns)
    numeric_cols = set(df.select_dtypes(include=[np.number]).columns)
    text_cols = set(df.columns) - datetime_cols - numeric_cols  # noqa: F841

    # Форматы
    fmt_datetime = 'YYYY-MM-DD HH:MM:SS'
    fmt_float = '0.000'
    fmt_int = '0'

    # Целочисленные колонки (битовые флаги, час, день недели и т.д.)
    int_like_cols = set()
    for c in numeric_cols:
        s = df[c].dropna()
        if len(s) > 0 and np.array_equal(s.values, s.values.astype(np.int64)):
            int_like_cols.add(c)

    # Заголовок
    ws.append(list(df.columns))

    columns = list(df.columns)

    # Запись построчно (write_only -> низкий memory footprint на 40k строк)
    for row_tuple in df.itertuples(index=False, name=None):
        row_cells = []
        for col_name, value in zip(columns, row_tuple):
            cell = WriteOnlyCell(ws, value=None)

            if pd.isna(value):
                cell.value = None
            elif col_name in datetime_cols:
                cell.value = value.to_pydatetime() if hasattr(value, 'to_pydatetime') else value
                cell.number_format = fmt_datetime
            elif col_name in numeric_cols:
                if col_name in int_like_cols:
                    cell.value = int(value)
                    cell.number_format = fmt_int
                else:
                    cell.value = float(value)
                    cell.number_format = fmt_float
            else:
                # Текстовые колонки: mode, failure_type — принудительно как строка
                cell.value = str(value)
                cell.number_format = xl_numbers.FORMAT_TEXT

            row_cells.append(cell)
        ws.append(row_cells)

    wb.save(path)


# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    df = build_dataset(CONFIG)
    validate_dataset(df, CONFIG)

    df_features = add_engineered_features(df, CONFIG)

    # --- Пути сохранения (только расширенный датасет) ---
    output_dir = os.path.abspath(os.getcwd())
    csv_path = os.path.join(output_dir, 'datacenter_energy_dataset_features.csv')
    xlsx_path = os.path.join(output_dir, 'datacenter_energy_dataset_features.xlsx')

    # --- CSV в европейском формате ---
    # sep=';'             -> разделитель столбцов
    # decimal=','         -> десятичная запятая (RU/EU Excel-friendly)
    # date_format         -> ISO для timestamp, чтобы Excel не путал день/месяц
    # encoding='utf-8-sig' -> Excel корректно открывает кириллицу
    df_features.to_csv(
        csv_path,
        index=False,
        sep=';',
        decimal=',',
        date_format='%Y-%m-%d %H:%M:%S',
        encoding='utf-8-sig',
    )

    # --- XLSX через openpyxl с типизацией ячеек ---
    save_xlsx_typed(df_features, xlsx_path)

    # --- Точные пути в консоль ---
    print(f"\n📁 Расширенный датасет сохранён в двух форматах:")
    print(f"   CSV : {csv_path}")
    print(f"   XLSX: {xlsx_path}")

    print(f"\n--- Первые 5 строк ---")
    print(df_features.head().to_string())

    print(f"\n--- Статистика ---")
    print(df_features.describe(include='all').round(2).to_string())
