#!/usr/bin/env python3
"""
Генератор отчёта по нештатным ситуациям с учётом температурного графика
"""

import json

# Типовые температурные графики
TEMP_GRAPHS = {
    "150/70": {  # Высокотемпературный (котловые)
        -30: (150, 70), -25: (140, 65), -20: (130, 60), -15: (120, 55),
        -10: (110, 50), -5: (100, 45), 0: (90, 40), 5: (80, 35), 10: (70, 30)
    },
    "95/70": {  # Классический
        -30: (115, 70), -25: (105, 65), -20: (95, 60), -15: (85, 55),
        -10: (75, 50), -5: (65, 45), 0: (55, 40), 5: (45, 35), 10: (40, 30)
    },
    "80/60": {  # Низкотемпературный
        -30: (80, 60), -25: (75, 55), -20: (70, 50), -15: (65, 48),
        -10: (60, 45), -5: (55, 40), 0: (50, 38), 5: (45, 35), 10: (40, 30)
    }
}

# Графики для разных объектов (можно настраивать)
OBJECT_GRAPHS = {
    "Индустрия": "150/70",  # котельная
    "котельная": "150/70",
    "ТСЖ": "95/70",
}

def get_temp_for_outdoor(t_out, graph):
    """Получить ожидаемые температуры"""
    temps = sorted(graph.keys())
    if t_out <= temps[0]: return graph[temps[0]]
    if t_out >= temps[-1]: return graph[temps[-1]]
    for i in range(len(temps)-1):
        if temps[i] <= t_out <= temps[i+1]:
            return graph[temps[i]]
    return graph[0]

def analyze():
    with open('/root/eldis/eldis-monitor/feb2026_readings.json', 'r') as f:
        readings = json.load(f)
    
    # Параметры анализа
    t_outdoor = -8  # Средняя для февраля
    tolerance = 10   # Допуск ±10°C
    
    # Группировка по объектам
    objects = {}
    for r in readings:
        addr = r.get('address', 'Unknown')
        if addr not in objects:
            objects[addr] = {
                'device': r.get('device_name'),
                'resource': r.get('resource_type'),
                'records': []
            }
        objects[addr]['records'].append(r)
    
    # Анализ
    results = []
    
    for addr, data in objects.items():
        records = data['records']
        total = len(records)
        
        # Определяем график
        graph_name = "95/70"  # default
        for key, g in OBJECT_GRAPHS.items():
            if key.lower() in addr.lower():
                graph_name = g
                break
        
        t1_exp, t2_exp = get_temp_for_outdoor(t_outdoor, TEMP_GRAPHS[graph_name])
        
        # Статистика
        ns_count = sum(1 for r in records if r.get('ns') == True)
        t1_values = [r.get('t1', 0) for r in records if r.get('t1')]
        t1_avg = sum(t1_values) / len(t1_values) if t1_values else 0
        t1_max = max(t1_values) if t1_values else 0
        t1_zero = sum(1 for r in records if not r.get('t1') or r.get('t1') == 0)
        
        # Нарушения графика
        graph_violations = sum(1 for r in records 
            if r.get('t1') and abs(r.get('t1', 0) - t1_exp) > tolerance)
        
        # V1 < V2
        v_violations = sum(1 for r in records 
            if (r.get('V1') or 0) > 0 and (r.get('V2') or 0) > 0 
            and r.get('V1') < r.get('V2'))
        
        results.append({
            'address': addr,
            'device': data['device'],
            'graph': graph_name,
            't_outdoor': t_outdoor,
            't1_expected': t1_exp,
            'total': total,
            'ns_count': ns_count,
            't1_avg': round(t1_avg, 1),
            't1_max': round(t1_max, 1),
            't1_zero': t1_zero,
            'graph_violations': graph_violations,
            'v_violations': v_violations
        })
    
    # Сортируем по ns_count
    results.sort(key=lambda x: x['ns_count'], reverse=True)
    
    return results

def generate_report():
    results = analyze()
    
    report = """
================================================================================
                     ОТЧЁТ ПО НЕШТАТНЫМ СИТУАЦИЯМ
                   С УЧЁТОМ ТЕМПЕРАТУРНОГО ГРАФИКА
================================================================================

ПЕРИОД: Февраль 2026 (01.02.2026 - 28.02.2026)
РАСЧЁТНАЯ НАРУЖНАЯ ТЕМПЕРАТУРА: -8°C
ДОПУСК: ±10°C

================================================================================
"""
    
    for i, r in enumerate(results, 1):
        if r['ns_count'] == 0 and r['graph_violations'] == 0:
            continue
            
        report += f"""
--------------------------------------------------------------------------------
ОБЪЕКТ #{i}
--------------------------------------------------------------------------------
Адрес:         {r['address']}
Прибор:        {r['device']}
График:        {r['graph']} (при tнар={r['t_outdoor']}°C → t1={r['t1_expected']}°C)

Статистика:
  Всего записей:              {r['total']}
  Нештатных ситуаций (ns):    {r['ns_count']} ({r['ns_count']/r['total']*100:.1f}%)
  Средняя t1:                 {r['t1_avg']}°C
  Максимальная t1:            {r['t1_max']}°C
  t1 = 0 (нет данных):        {r['t1_zero']}
  Нарушений графика:          {r['graph_violations']}
  V1 < V2:                   {r['v_violations']}
"""
    
    # Сохраняем
    with open('/root/eldis/eldis-monitor/NS_report_temp_graph.txt', 'w', encoding='utf-8') as f:
        f.write(report)
    
    print(report)
    print("\nСохранено в NS_report_temp_graph.txt")

if __name__ == "__main__":
    generate_report()
