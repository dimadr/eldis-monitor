#!/usr/bin/env python3
"""
Анализ нештатных ситуаций с учётом температурного графика
"""

import json
from datetime import datetime

# Типовые температурные графики (зависимость от наружной температуры)
# Формат: {tнар: (t1_подача, t2_обратка)}
TEMP_GRAPHS = {
    # График 95/70
    "95/70": {
        -30: (115, 70), -25: (105, 65), -20: (95, 60), -15: (85, 55),
        -10: (75, 50), -5: (65, 45), 0: (55, 40), 5: (45, 35), 10: (40, 30)
    },
    # График 150/70 (высокотемпературный)
    "150/70": {
        -30: (150, 70), -25: (140, 65), -20: (130, 60), -15: (120, 55),
        -10: (110, 50), -5: (100, 45), 0: (90, 40), 5: (80, 35), 10: (70, 30)
    },
    # График 80/60 (низкотемпературный)
    "80/60": {
        -30: (80, 60), -25: (75, 55), -20: (70, 50), -15: (65, 48),
        -10: (60, 45), -5: (55, 40), 0: (50, 38), 5: (45, 35), 10: (40, 30)
    },
    # График 90/50
    "90/50": {
        -30: (90, 50), -25: (85, 48), -20: (80, 45), -15: (75, 42),
        -10: (70, 40), -5: (65, 38), 0: (60, 35), 5: (55, 32), 10: (50, 30)
    }
}

def get_expected_temp(t_outdoor, graph_name="150/70"):
    """Получить ожидаемые температуры по графику"""
    graph = TEMP_GRAPHS.get(graph_name, TEMP_GRAPHS["150/70"])
    
    temps = sorted(graph.keys())
    
    # Находим ближайшую точку
    if t_outdoor <= temps[0]:
        return graph[temps[0]]
    elif t_outdoor >= temps[-1]:
        return graph[temps[-1]]
    else:
        for i in range(len(temps) - 1):
            if temps[i] <= t_outdoor <= temps[i+1]:
                return graph[temps[i]]
    
    return graph[0]  # fallback

def analyze_with_temp_graph(readings, t_outdoor, graph_name="150/70", tolerance=5):
    """
    Анализ с учётом температурного графика
    
    Args:
        readings: список показаний
        t_outdoor: наружная температура (средняя за период)
        graph_name: имя графика
        tolerance: допуск в градусах
    """
    t1_expected, t2_expected = get_expected_temp(t_outdoor, graph_name)
    
    results = {
        't1_expected': t1_expected,
        't2_expected': t2_expected,
        't_outdoor': t_outdoor,
        'graph': graph_name,
        'anomalies': []
    }
    
    for r in readings:
        t1 = r.get('t1') or 0
        t2 = r.get('t2') or 0
        
        if t1 == 0 or t2 == 0:
            continue
        
        # Проверяем отклонение
        t1_deviation = abs(t1 - t1_expected)
        t2_deviation = abs(t2 - t2_expected)
        
        if t1_deviation > tolerance:
            results['anomalies'].append({
                'type': 't1_deviation',
                'date': r.get('date'),
                't1_actual': t1,
                't1_expected': t1_expected,
                'deviation': t1_deviation
            })
        
        if t2_deviation > tolerance:
            results['anomalies'].append({
                'type': 't2_deviation',
                'date': r.get('date'),
                't2_actual': t2,
                't2_expected': t2_expected,
                'deviation': t2_deviation
            })
    
    return results

def analyze_all_objects(readings):
    """Анализ всех объектов"""
    # Типовые графики по умолчанию
    default_graph = "150/70"
    t_outdoor_feb = -8  # Типовая для февраля в Ивановской области
    
    # Группируем по адресу
    objects = {}
    for r in readings:
        addr = r.get('address', 'Unknown')
        if addr not in objects:
            objects[addr] = []
        objects[addr].append(r)
    
    report = []
    
    for addr, data in objects.items():
        if not data:
            continue
            
        device = data[0].get('device_name', 'Unknown')
        
        # Базовые проверки
        ns_count = sum(1 for r in data if r.get('ns') == True)
        t1_high = sum(1 for r in data if (r.get('t1') or 0) > 150)
        t1_avg = sum(r.get('t1', 0) for r in data if r.get('t1')) / max(1, sum(1 for r in data if r.get('t1')))
        
        # Анализ по графику
        t1_exp, t2_exp = get_expected_temp(t_outdoor_feb, default_graph)
        
        # Проверка по графику
        graph_violations = 0
        for r in data:
            t1 = r.get('t1') or 0
            t2 = r.get('t2') or 0
            if t1 > 0 and abs(t1 - t1_exp) > 10:
                graph_violations += 1
        
        if ns_count > 0 or t1_high > 0 or graph_violations > 0:
            report.append({
                'address': addr[:50],
                'device': device,
                'total': len(data),
                'ns_count': ns_count,
                't1_high': t1_high,
                't1_avg': round(t1_avg, 1),
                'expected_t1': t1_exp,
                'graph_violations': graph_violations
            })
    
    return sorted(report, key=lambda x: x['ns_count'], reverse=True)

if __name__ == "__main__":
    with open('/root/eldis/eldis-monitor/feb2026_readings.json', 'r') as f:
        readings = json.load(f)
    
    print("=" * 60)
    print("АНАЛИЗ С УЧЁТОМ ТЕМПЕРАТУРНОГО ГРАФИКА")
    print("=" * 60)
    print(f"Период: Февраль 2026")
    print(f"Расчётная наружная температура: -8°C")
    print(f"График: 150/70")
    print(f"Ожидаемая t1: 110°C, t2: 45°C")
    print("=" * 60)
    
    results = analyze_all_objects(readings)
    
    for r in results[:10]:
        print(f"\n{r['address']}")
        print(f"  Прибор: {r['device']}")
        print(f"  Записей: {r['total']}, ns=true: {r['ns_count']}")
        print(f"  t1 средняя: {r['t1_avg']}°C (ожидается: {r['expected_t1']}°C)")
        print(f"  Нарушений графика: {r['graph_violations']}")
