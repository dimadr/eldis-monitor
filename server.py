import os
import json
import requests
import sqlite3
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash
from openai import OpenAI

# Импорт универсального анализатора
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'scripts'))
from universal_analyzer import create_analyzer as create_universal_analyzer

from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, '.env'))
HTML_DIR = os.path.join(BASE_DIR, 'html')
TEMPLATE_DIR = os.path.join(BASE_DIR, 'templates')
os.makedirs(HTML_DIR, exist_ok=True)

app = Flask(__name__, template_folder=TEMPLATE_DIR)
app.secret_key = 'eldis-monitor-secret-key'

ELDIS_API_URL = os.getenv('ELDIS_API_URL', 'https://api.eldis24.ru')
ELDIS_LOGIN = os.getenv('ELDIS_LOGIN', '')
ELDIS_PASSWORD = os.getenv('ELDIS_PASSWORD', '')
ELDIS_API_KEY = os.getenv('ELDIS_API_KEY', '')

OPENCODE_CONFIG = os.path.join(BASE_DIR, '..', 'opencode.json')

def load_ai_models():
    """Загружает список AI моделей из opencode.json.
       Для RouterAI ключ читается из .env (ROUTERAI_API_KEY), если не указан в файле."""
    try:
        with open(OPENCODE_CONFIG, 'r') as f:
            config = json.load(f)
        
        routerai_key = os.environ.get('ROUTERAI_API_KEY', '')
        
        models = []
        for provider, data in config.get('provider', {}).items():
            for model_id, model_data in data.get('models', {}).items():
                api_key = data.get('options', {}).get('apiKey', '')
                if not api_key and provider == 'RouterAI':
                    api_key = routerai_key
                models.append({
                    'id': f"{provider}:{model_id}",
                    'name': model_data.get('name', model_id),
                    'provider': provider,
                    'base_url': data.get('options', {}).get('baseURL', ''),
                    'api_key': api_key
                })
        return models
    except Exception as e:
        print(f"Error loading AI models: {e}")
        return []

AI_MODELS = load_ai_models()

def eldis_login():
    """Авторизация в ELDIS API"""
    url = f"{ELDIS_API_URL}/api/v2/users/login"
    data = {
        "login": ELDIS_LOGIN,
        "password": ELDIS_PASSWORD,
    }
    headers = {
        "key": ELDIS_API_KEY,
        "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
    }
    
    response = requests.post(url, data=data, headers=headers, timeout=30)
    response.raise_for_status()
    
    access_token = response.cookies.get("access_token")
    if not access_token:
        set_cookie = response.headers.get('Set-Cookie', '')
        import re
        match = re.search(r'access_token=([^;]+)', set_cookie)
        if match:
            access_token = match.group(1)
    
    return access_token

def get_device_data(device_id, token, start_date=None, end_date=None):
    """Получить данные прибора"""
    url = f"{ELDIS_API_URL}/api/v2/tv/listForDevelopment"
    headers = {"key": ELDIS_API_KEY}
    cookies = {"access_token": token}
    
    response = requests.get(url, headers=headers, cookies=cookies, timeout=30)
    response.raise_for_status()
    
    data = response.json()
    devices_raw = data.get("response", {}).get("tv", {}).get("listForDevelopment", {})
    
    devices = {}
    if isinstance(devices_raw, dict):
        devices = devices_raw
    elif isinstance(devices_raw, list):
        for item in devices_raw:
            if isinstance(item, dict) and 'id' in item:
                devices[str(item['id'])] = item
    
    device = devices.get(str(device_id)) or devices.get(device_id)
    if device is None:
        return {"id": device_id, "name": f"Объект {device_id}", "type": "unknown"}
    return device

def get_readings(device_id, token, archive_type=30004, start_date=None, end_date=None):
    """Получить показания прибора"""
    url = f"{ELDIS_API_URL}/api/v1/data/normalized"
    headers = {"key": ELDIS_API_KEY}
    cookies = {"access_token": token}
    
    params = {
        "id": device_id,
        "typeDataCode": archive_type,
    }
    if start_date:
        params["startDate"] = start_date
    if end_date:
        params["endDate"] = end_date
    
    response = requests.get(url, headers=headers, cookies=cookies, params=params, timeout=30)
    response.raise_for_status()
    data = response.json()
    
    normalized = data.get('response', {}).get('data', {}).get('normalized', [])
    
    # Check if daily data is complete
    records_with_data = 0
    for item in normalized:
        for res_type, records in item.items():
            for rec in records:
                if rec.get('Q') is not None or rec.get('M1') is not None:
                    records_with_data += 1
    
    expected_days = 28
    if start_date and end_date:
        from datetime import datetime
        try:
            d1 = datetime.strptime(start_date, '%Y-%m-%d')
            d2 = datetime.strptime(end_date, '%Y-%m-%d')
            expected_days = (d2 - d1).days + 1
        except:
            pass
    
    # If daily data is incomplete, get hourly and aggregate
    if records_with_data < expected_days * 0.5:
        # For hourly data, request without date limits to get full month
        params_hourly = {
            "id": device_id,
            "typeDataCode": 30003,
        }
        try:
            response2 = requests.get(url, headers=headers, cookies=cookies, params=params_hourly, timeout=60)
            if response2.status_code == 200:
                hourly_data = response2.json()
                hourly_normalized = hourly_data.get('response', {}).get('data', {}).get('normalized', [])
                
                from collections import defaultdict
                daily = defaultdict(lambda: {'t1': [], 't2': [], 'M1': 0, 'M2': 0, 'V1': 0, 'V2': 0, 'Q': 0, 'P1': None, 'P2': None, 'QntHIP': 0})
                
                for item in hourly_normalized:
                    for res_type, records in item.items():
                        for rec in records:
                            from datetime import datetime
                            try:
                                dt = datetime.fromtimestamp(rec.get('date', 0))
                                day = dt.strftime('%Y-%m-%d')
                            except:
                                continue
                            
                            if rec.get('t1') is not None:
                                daily[day]['t1'].append(rec['t1'])
                            if rec.get('t2') is not None:
                                daily[day]['t2'].append(rec['t2'])
                            # Sum dM, dV, Q for the day
                            if rec.get('dM') is not None:
                                daily[day]['M1'] += rec.get('dM', 0)
                                daily[day]['M2'] += rec.get('dM', 0)
                            if rec.get('dV') is not None:
                                daily[day]['V1'] += rec.get('dV', 0)
                                daily[day]['V2'] += rec.get('dV', 0)
                            if rec.get('Q') is not None:
                                daily[day]['Q'] += rec['Q']
                            if rec.get('P1') is not None and daily[day]['P1'] is None:
                                daily[day]['P1'] = rec['P1']
                            if rec.get('P2') is not None and daily[day]['P2'] is None:
                                daily[day]['P2'] = rec['P2']
                            if rec.get('QntHIP'):
                                daily[day]['QntHIP'] = max(daily[day]['QntHIP'], rec.get('QntHIP', 0))
                
                aggregated = []
                for day in sorted(daily.keys()):
                    vals = daily[day]
                    t1_avg = sum(vals['t1']) / len(vals['t1']) if vals['t1'] else None
                    t2_avg = sum(vals['t2']) / len(vals['t2']) if vals['t2'] else None
                    
                    rec = {
                        'date': int(datetime.strptime(day, '%Y-%m-%d').timestamp()),
                        't1': round(t1_avg, 2) if t1_avg else None,
                        't2': round(t2_avg, 2) if t2_avg else None,
                        'dt': round(t1_avg - t2_avg, 2) if t1_avg and t2_avg else None,
                        'M1': round(vals['M1'], 3),
                        'M2': round(vals['M2'], 3),
                        'dM': round(vals['M1'] - vals['M2'], 3),
                        'V1': round(vals['V1'], 2),
                        'V2': round(vals['V2'], 2),
                        'dV': round(vals['V1'] - vals['V2'], 2),
                        'Q': round(vals['Q'], 3),
                        'P1': vals['P1'],
                        'P2': vals['P2'],
                        'QntHIP': vals['QntHIP'],
                    }
                    aggregated.append(rec)
                
                data['response']['data']['normalized'] = [{'hotWater': aggregated}]
        except Exception as e:
            print(f"Aggregation error: {e}")
    
    return data

def load_ns_dictionary():
    """Загрузить справочник формул"""
    ns_dict_path = os.path.join(BASE_DIR, 'ns_dictionary.json')
    try:
        with open(ns_dict_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}

def process_readings(readings):
    """Обработать показания в табличный формат"""
    table = []
    try:
        normalized = readings.get('response', {}).get('data', {}).get('normalized', {})
        
        if isinstance(normalized, list):
            for item in normalized:
                if isinstance(item, dict):
                    for resource_type, records in item.items():
                        if isinstance(records, list):
                            for record in records:
                                row = parse_record(record)
                                if row:
                                    row['type'] = resource_type
                                    # Маппинг для ГВС: t1->t3, V1->V3, M1->M3, Q->Qg
                                    if resource_type == 'hotWater':
                                        if 't1' in row:
                                            row['t3'] = row.pop('t1')
                                        if 'V1' in row:
                                            row['V3'] = row.pop('V1')
                                        if 'M1' in row:
                                            row['M3'] = row.pop('M1')
                                        if 'Q' in row:
                                            row['Qg'] = row.pop('Q')
                                    table.append(row)
        elif isinstance(normalized, dict):
            for device_id, records in normalized.items():
                if isinstance(records, list):
                    for record in records:
                        row = parse_record(record)
                        if row:
                            table.append(row)
                elif isinstance(records, dict):
                    for resource_type, rec_list in records.items():
                        if isinstance(rec_list, list):
                            for record in rec_list:
                                row = parse_record(record)
                                if row:
                                    row['type'] = resource_type
                                    # Маппинг для ГВС
                                    if resource_type == 'hotWater':
                                        if 't1' in row:
                                            row['t3'] = row.pop('t1')
                                        if 'V1' in row:
                                            row['V3'] = row.pop('V1')
                                        if 'M1' in row:
                                            row['M3'] = row.pop('M1')
                                        if 'Q' in row:
                                            row['Qg'] = row.pop('Q')
                                    table.append(row)
    except Exception as e:
        print(f"Error processing readings: {e}")
    return table

def parse_record(record):
    """Парсить одну запись показаний"""
    if not isinstance(record, dict):
        return None
    
    row = {}
    
    if 'date' in record:
        from datetime import datetime
        try:
            dt = datetime.fromtimestamp(record['date'])
            row['timestamp'] = dt.strftime('%Y-%m-%d %H:%M')
        except:
            row['timestamp'] = str(record.get('date', ''))
    else:
        row['timestamp'] = ''
    
    for key in ['t1', 't2', 't3', 'M1', 'M2', 'M3', 'V1', 'V2', 'V3', 'Q', 'dt', 'dV', 'dM', 'P1', 'P2', 'tcw', 'Qg']:
        if key in record and record[key] is not None:
            row[key] = record[key]
    
    # Поля прибора МКТС (теплосчётчик с иной схемой данных)
    for key in ['Mg', 'Primes', 'ta', 'Tраб', 'NS', 'QntP']:
        if key in record and record[key] is not None:
            row[key] = record[key]
    # Поле % (процент небаланса, API может отдавать как ключ)
    if '%' in record and record['%'] is not None:
        row['pct'] = record['%']
    # Кириллические ключи (Вр.раб1, Вр.раб2, Вр.раб3)
    if 'Вр.раб1' in record and record['Вр.раб1'] is not None:
        row['hr1'] = record['Вр.раб1']
    if 'Вр.раб2' in record and record['Вр.раб2'] is not None:
        row['hr2'] = record['Вр.раб2']
    if 'Вр.раб3' in record and record['Вр.раб3'] is not None:
        row['hr3'] = record['Вр.раб3']
    
    if 'ns' in record:
        row['ns'] = record['ns']
    elif 'NS' in record:
        row['ns'] = record['NS']
    if 'QntHIP' in record:
        row['QntHIP'] = record['QntHIP']
    if 'QntP' in record:
        row['QntP'] = record['QntP']
    
    return row if row else None

def analyze_with_ai(data, model_id, ns_dictionary):
    """Анализ данных с помощью AI - с рекомендациями для сервисного инженера"""
    model = next((m for m in AI_MODELS if m['id'] == model_id), None)
    if not model:
        return None
    
    if not model.get('api_key'):
        return None
    
    checks = data.get('checks', [])
    
    if not checks:
        return "Нет данных для анализа"
    
    error_count = sum(1 for c in checks if c.get('status') == 'error')
    ok_count = sum(1 for c in checks if c.get('status') == 'ok')
    
    # Simple analysis first
    result = f"Проверено {len(checks)} показателей: {ok_count} - ошибок не выявлено"
    if error_count > 0:
        result += f", {error_count} - найдены ошибки"
    
    error_details = [c for c in checks if c.get('status') == 'error']
    if error_details:
        result += ". Ошибки: " + "; ".join([f"{c['name']}: {c.get('description', c.get('result', ''))}" for c in error_details])
    
    # Now call AI for detailed analysis
    try:
        from openai import OpenAI
        client = OpenAI(
            base_url=model['base_url'],
            api_key=model['api_key']
        )
        
        readings_table = data.get('display_table', [])[:10]  # First 10 records for context
        
        system_prompt = """Ты - эксперт по анализу данных приборов учёта тепла, воды и ГВС.
Когда обнаружены нештатные ситуации (НС), ты должен:
1. Кратко описать тип НС
2. Объяснить возможные причины возникновения
3. Дать конкретные рекомендации сервисному инженеру по устранению

Отвечай кратко и по существу. Используй таблицу если нужно."""

        # Build analysis based on checks
        analysis_text = f"""Проанализируй данные прибора учёта и проверки:
        
Результаты проверок:
"""
        for check in checks:
            status = "ОК" if check.get('status') == 'ok' else "ОШИБКА"
            analysis_text += f"- {check['name']}: {status}\n"
            if check.get('description'):
                analysis_text += f"  {check['description']}\n"
        
        if error_details:
            analysis_text += """
Для каждой ошибки укажи:
1. Вероятная причина
2. Что проверить/сделать сервисному инженеру

Формат ответа:
### [Название НС]
**Причина:** ...
**Рекомендация:** ..."""

        response = client.chat.completions.create(
            model=model['name'],
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": analysis_text}
            ],
            temperature=0.3
        )
        
        ai_analysis = response.choices[0].message.content
        return result + "\n\n" + ai_analysis
        
    except Exception as e:
        print(f"AI Error: {e}")
        return result

def get_all_inputs_for_device(any_id):
    """По любому ID (Eldis, objectID, deviceID) найти все вводы прибора в mapping.db"""
    mapping_file = os.path.join(BASE_DIR, '..', 'mapping.db')
    if not os.path.exists(mapping_file):
        return []
    try:
        conn = sqlite3.connect(mapping_file)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Поиск: сначала по id (Eldis ID), потом по objectID, потом по deviceID
        found_object_id = None
        found_device_id = None
        matched_by = None
        
        for column in ['id', 'objectID', 'deviceID']:
            cursor.execute(f'SELECT objectID, deviceID FROM mappings WHERE {column} = ? LIMIT 1', (any_id,))
            row = cursor.fetchone()
            if row:
                found_object_id = row['objectID']
                found_device_id = row['deviceID']
                matched_by = column
                break
        
        if not found_device_id:
            conn.close()
            return []
        
        # Если нашли по objectID — вернуть ВСЕ вводы всех приборов объекта
        if matched_by == 'objectID':
            cursor.execute('''
                SELECT id, resourceName, measurePointName, deviceID 
                FROM mappings WHERE objectID = ?
            ''', (found_object_id,))
        else:
            # По id или deviceID — вернуть вводы одного прибора
            cursor.execute('''
                SELECT id, resourceName, measurePointName, deviceID 
                FROM mappings WHERE deviceID = ?
            ''', (found_device_id,))
        
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return rows
    except Exception as e:
        print(f"Ошибка поиска вводов: {e}")
        return []

@app.route('/')
def index():
    return render_template('index.html', models=AI_MODELS)

@app.route('/generate', methods=['POST'])
def generate():
    device_id = request.form.get('device_id', '').strip()
    address = request.form.get('address', '').strip()
    device_name = request.form.get('device_name', '').strip()
    device_code = request.form.get('device_code', '').strip()
    start_date = request.form.get('start_date', '').strip()
    end_date = request.form.get('end_date', '').strip()
    model_id = request.form.get('model_id', '')
    report_type = request.form.get('report_type', 'object')
    
    if not device_id:
        flash('ID устройства обязателен')
        return redirect(url_for('index'))
    
    try:
        token = eldis_login()
        
        device_info = get_device_data(device_id, token, start_date, end_date)
        
        # Найти все вводы прибора и опросить каждый
        all_inputs = get_all_inputs_for_device(device_id)
        queried_ids = set()
        all_readings = []
        
        # Всегда опрашиваем исходный ID
        r = get_readings(device_id, token, start_date=start_date, end_date=end_date)
        if r:
            all_readings.append(r)
        queried_ids.add(device_id)
        
        # Опрашиваем остальные вводы
        if all_inputs:
            for inp in all_inputs:
                inp_id = inp['id']
                if inp_id not in queried_ids:
                    queried_ids.add(inp_id)
                    r = get_readings(inp_id, token, start_date=start_date, end_date=end_date)
                    if r:
                        all_readings.append(r)
        
        
        # Объединить все показания
        combined = {'response': {'data': {'normalized': []}}}
        all_types = []
        for r in all_readings:
            if not r:
                continue
            norm = r.get('response', {}).get('data', {}).get('normalized', [])
            if isinstance(norm, list):
                for item in norm:
                    if isinstance(item, dict):
                        for rtype, records in item.items():
                            if isinstance(records, list) and records:
                                combined['response']['data']['normalized'].append(item)
                                if rtype not in all_types:
                                    all_types.append(rtype)
        
        readings_table = process_readings(combined)
        
        data = {
            'device_id': device_id,
            'address': address or device_info.get('address', ''),
            'device_name': device_name or device_info.get('deviceName', '') or device_info.get('customModelName', ''),
            'device_code': device_code or str(device_info.get('deviceCode', '')),
            'device_type': device_info.get('resourceName', ''),
            'counterparty': device_info.get('counterpartyName', ''),
            'device_number': device_info.get('sn', ''),
            'measure_point': device_info.get('measurePointName', ''),
            'modem': device_info.get('modemSN', ''),
            'device_info': device_info,
            'readings': combined,
            'readings_table': readings_table,
            'report_type': report_type,
            'start_date': start_date,
            'end_date': end_date,
            'generated_at': datetime.now().strftime('%d.%m.%Y %H:%M:%S')
        }
        
        # Фильтрация по типу отчёта
        if report_type == 'heat':
            data['display_table'] = [r for r in readings_table if r.get('type') == 'heat']
        elif report_type == 'hotWater':
            data['display_table'] = [r for r in readings_table if r.get('type') == 'hotWater']
        elif report_type == 'coldWater':
            data['display_table'] = [r for r in readings_table if r.get('type') == 'coldWater']
        elif report_type == 'drainage':
            data['display_table'] = [r for r in readings_table if r.get('type') == 'drainage']
        elif report_type == 'object':
            # Объединяем heat и hotWater по дате
            merged = {}
            for r in readings_table:
                date = r.get('timestamp', '')[:10]
                if date not in merged:
                    merged[date] = {'timestamp': date}
                # Для heat - все поля
                if r.get('type') == 'heat':
                    for k, v in r.items():
                        if v is not None and k != 'type':
                            merged[date][k] = v
                    # Вычисляем dM для строк (округляем до 2 знаков)
                    if 'M1' in merged[date] and 'M2' in merged[date]:
                        merged[date]['Mг'] = round(merged[date].get('M1', 0) - merged[date].get('M2', 0), 2)
                # Для hotWater - только специфичные
                elif r.get('type') == 'hotWater':
                    if 't3' not in merged[date] and r.get('t3') is not None:
                        merged[date]['t3'] = r.get('t3')
                    if 'M3' not in merged[date] and r.get('M3') is not None:
                        merged[date]['M3'] = r.get('M3')
                    if 'V3' not in merged[date] and r.get('V3') is not None:
                        merged[date]['V3'] = r.get('V3')
                    if 'Qg' not in merged[date] and r.get('Qg') is not None:
                        merged[date]['Qg'] = r.get('Qg')
            data['display_table'] = list(merged.values())
        else:
            data['display_table'] = readings_table
        
        # Определение колонок для таблицы - фиксированный порядок как в ЭЛДИС
        if report_type == 'object':
            data['table_columns'] = ['t1', 't2', 't3', 'dt', 'V1', 'V2', 'V3', 'M1', 'M2', 'M3', 'Mг', 'P1', 'P2', 'Q', 'Qg', 'QntHIP', 'VOCR']
        
        # Calculate totals - в зависимости от типа отчёта
        if readings_table:
            if report_type == 'heat':
                filtered = [r for r in readings_table if r.get('type') == 'heat']
            elif report_type == 'hotWater':
                filtered = [r for r in readings_table if r.get('type') == 'hotWater']
            elif report_type == 'object':
                # Для "Потребление объекта" - раздельные итоги
                heat_only = [r for r in readings_table if r.get('type') == 'heat']
                hotwater_only = [r for r in readings_table if r.get('type') == 'hotWater']
                
                heat_totals = None
                if heat_only:
                    heat_totals = {
                        't1_avg': sum(r.get('t1', 0) for r in heat_only if r.get('t1')) / len([r for r in heat_only if r.get('t1')]) if any(r.get('t1') for r in heat_only) else None,
                        't2_avg': sum(r.get('t2', 0) for r in heat_only if r.get('t2')) / len([r for r in heat_only if r.get('t2')]) if any(r.get('t2') for r in heat_only) else None,
                        'V1_sum': sum(r.get('V1', 0) for r in heat_only if r.get('V1')),
                        'V2_sum': sum(r.get('V2', 0) for r in heat_only if r.get('V2')),
                        'M1_sum': sum(r.get('M1', 0) for r in heat_only if r.get('M1')),
                        'M2_sum': sum(r.get('M2', 0) for r in heat_only if r.get('M2')),
                        'Q_sum': sum(r.get('Q', 0) for r in heat_only if r.get('Q')),
                        'hours': sum(r.get('QntHIP', 0) for r in heat_only if r.get('QntHIP')),
                    }
                
                hotwater_totals = None
                if hotwater_only:
                    hotwater_totals = {
                        't3_avg': sum(r.get('t3', 0) for r in hotwater_only if r.get('t3')) / len([r for r in hotwater_only if r.get('t3')]) if any(r.get('t3') for r in hotwater_only) else None,
                        'V3_sum': sum(r.get('V3', 0) for r in hotwater_only if r.get('V3')),
                        'M3_sum': sum(r.get('M3', 0) for r in hotwater_only if r.get('M3')),
                        'Qg_sum': sum(r.get('Qg', 0) for r in hotwater_only if r.get('Qg')),
                    }
                
                # Средние значения
                data['averages'] = {}
                if heat_only:
                    t1_vals = [r.get('t1') for r in heat_only if r.get('t1') is not None]
                    t2_vals = [r.get('t2') for r in heat_only if r.get('t2') is not None]
                    dt_vals = [r.get('dt') for r in heat_only if r.get('dt') is not None]
                    if t1_vals:
                        data['averages']['t1'] = sum(t1_vals) / len(t1_vals)
                    if t2_vals:
                        data['averages']['t2'] = sum(t2_vals) / len(t2_vals)
                    if dt_vals:
                        data['averages']['dt'] = sum(dt_vals) / len(dt_vals)
                if hotwater_only:
                    t3_vals = [r.get('t3') for r in hotwater_only if r.get('t3') is not None]
                    if t3_vals:
                        data['averages']['t3'] = sum(t3_vals) / len(t3_vals)
                
                # Суммы
                data['totals'] = {}
                if heat_only:
                    data['totals']['V1'] = sum(r.get('V1', 0) for r in heat_only if r.get('V1'))
                    data['totals']['V2'] = sum(r.get('V2', 0) for r in heat_only if r.get('V2'))
                    data['totals']['M1'] = sum(r.get('M1', 0) for r in heat_only if r.get('M1'))
                    data['totals']['M2'] = sum(r.get('M2', 0) for r in heat_only if r.get('M2'))
                    data['totals']['Q'] = sum(r.get('Q', 0) for r in heat_only if r.get('Q'))
                    data['totals']['Mг'] = data['totals'].get('M1', 0) - data['totals'].get('M2', 0)
                    data['totals']['dM'] = data['totals']['Mг']
                    data['totals']['dV'] = data['totals'].get('V1', 0) - data['totals'].get('V2', 0)
                    data['totals']['QntHIP'] = sum(r.get('QntHIP', 0) for r in heat_only if r.get('QntHIP'))
                if hotwater_only:
                    data['totals']['V3'] = sum(r.get('V3', 0) for r in hotwater_only if r.get('V3'))
                    data['totals']['M3'] = sum(r.get('M3', 0) for r in hotwater_only if r.get('M3'))
                    data['totals']['Qg'] = sum(r.get('Qg', 0) for r in hotwater_only if r.get('Qg'))
                filtered = readings_table
                filtered = readings_table  # для проверок - всё
            else:
                filtered = readings_table
            
            # Для одиночных типов (не object)
            if report_type != 'object' and filtered:
                data['totals'] = {
                    't1_avg': sum(r.get('t1', 0) for r in filtered if r.get('t1')) / len([r for r in filtered if r.get('t1')]) if any(r.get('t1') for r in filtered) else None,
                    't2_avg': sum(r.get('t2', 0) for r in filtered if r.get('t2')) / len([r for r in filtered if r.get('t2')]) if any(r.get('t2') for r in filtered) else None,
                    'V1_sum': sum(r.get('V1', 0) for r in filtered if r.get('V1')),
                    'V2_sum': sum(r.get('V2', 0) for r in filtered if r.get('V2')),
                    'M1_sum': sum(r.get('M1', 0) for r in filtered if r.get('M1')),
                    'M2_sum': sum(r.get('M2', 0) for r in filtered if r.get('M2')),
                    'Q_sum': sum(r.get('Q', 0) for r in filtered if r.get('Q')),
                    'hours': sum(r.get('QntHIP', 0) for r in filtered if r.get('QntHIP')),
                    'count': len(filtered)
                }
        
        ns_dictionary = load_ns_dictionary()
        
        data['checks'] = perform_checks(data, ns_dictionary)
        
        # AI анализ с универсальным анализатором
        device_code = data.get('device_code', '')
        device_name = data.get('device_name', '')
        
        # Подготовить данные для анализатора
        checks_for_analyzer = {}
        for check in data['checks']:
            if check['name'] == 'Небаланс масс' and check['status'] == 'error':
                import re
                m = re.search(r'(-?[\d.]+)%', check.get('value', ''))
                if m:
                    checks_for_analyzer['mass_imbalance'] = float(m.group(1))
            elif check['name'] == 'Разница температур dt >= 2°C' and check['status'] == 'error':
                import re
                m = re.search(r'(-?[\d.]+)°C', check.get('value', ''))
                if m:
                    checks_for_analyzer['negative_dt'] = float(m.group(1))
            elif check['name'] == 'Нештатные ситуации' and check['status'] == 'error':
                import re
                m = re.search(r'(\d+)\s*записей', check.get('value', ''))
                if m:
                    checks_for_analyzer['ns_events'] = int(m.group(1))
        
        # Запустить анализ
        if not readings_table:
            data['universal_analysis'] = '<p>За указанный период данных нет.</p>'
            data['analysis'] = ''
        else:
            if checks_for_analyzer:
                universal_analyzer = create_universal_analyzer()
                analysis_result = universal_analyzer.analyze(
                    device_code=device_code,
                    device_name=device_name,
                    checks=checks_for_analyzer
                )
                data['universal_analysis'] = universal_analyzer.format_html(analysis_result)
            else:
                data['universal_analysis'] = '<p>Все показания в норме. Отклонений не выявлено.</p>'
            
            if model_id:
                analysis = analyze_with_ai(data, model_id, ns_dictionary)
                data['analysis'] = analysis
        
        filename = f"{device_id}_{datetime.now().strftime('%d.%m.%Y')}.html"
        filename = sanitize_filename(filename)
        filepath = os.path.join(HTML_DIR, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(render_template('report.html', **data))
        
        flash(f'Отчёт сохранён: {filename}')
        return render_template('report.html', **data, saved_file=filename)
        
    except Exception as e:
        flash(f'Ошибка: {str(e)}')
        return redirect(url_for('index'))

def perform_checks(data, ns_dictionary):
    """Выполнить проверки данных по формулам из справочника"""
    checks = []
    readings_table = data.get('readings_table', [])
    
    if not readings_table:
        return checks
    
    # Группировка по типу - отдельно heat и hotWater
    heat_readings = [r for r in readings_table if r.get('type') == 'heat']
    hotwater_readings = [r for r in readings_table if r.get('type') == 'hotWater']
    
    # Для heat - проверяем небаланс масс и dt
    if heat_readings:
        M1_heat = [r.get('M1', 0) for r in heat_readings if r.get('M1') is not None]
        M2_heat = [r.get('M2', 0) for r in heat_readings if r.get('M2') is not None]
        
        if M1_heat and M2_heat:
            M1_avg = sum(M1_heat) / len(M1_heat)
            M2_avg = sum(M2_heat) / len(M2_heat)
            if M1_avg > 0:
                imbalance = ((M1_avg - M2_avg) / M1_avg) * 100
                status = 'ok' if -2 <= imbalance <= 2 else 'error'
                result_str = 'Ошибок не выявлено' if status == 'ok' else 'Найдена ошибка'
                check = {
                    'name': 'Небаланс масс',
                    'formula': '((M1-M2)/M1)*100%',
                    'value': f'{imbalance:.2f}%',
                    'result': result_str,
                    'status': status
                }
                if status == 'error':
                    check['description'] = f'Отклонение {imbalance:.2f}% выходит за пределы ±2%'
                checks.append(check)
            else:
                checks.append({
                    'name': 'Небаланс масс',
                    'formula': '((M1-M2)/M1)*100%',
                    'result': 'M1 = 0, проверка невозможна',
                    'status': 'ok'
                })
        else:
            checks.append({
                'name': 'Небаланс масс',
                'formula': '((M1-M2)/M1)*100%',
                'result': 'Нет данных M1/M2 для проверки',
                'status': 'ok'
            })
    else:
        checks.append({
            'name': 'Небаланс масс',
            'formula': '((M1-M2)/M1)*100%',
            'result': 'Нет данных по теплу для проверки',
            'status': 'ok'
        })
    
    # Для hotWater - отдельные проверки (без M2 и t2)
    
    # Собираем значения для остальных проверок
    all_readings = readings_table
    M1_values = [r.get('M1', 0) for r in all_readings if r.get('M1') is not None]
    t1_values = [r.get('t1', 0) for r in all_readings if r.get('t1') is not None]
    Q_values = [r.get('Q', 0) for r in all_readings if r.get('Q') is not None]
    ns_values = [r.get('ns', False) for r in all_readings]
    
    # Проверка отсутствия массы - для всех типов
    has_mass_absence = False
    for i in range(len(readings_table)):
        m1 = readings_table[i].get('M1', 0)
        t1 = readings_table[i].get('t1', 0)
        if m1 is not None and t1 is not None and m1 <= 0 and t1 > 30:
            has_mass_absence = True
            break
    if has_mass_absence:
        checks.append({
            'name': 'Отсутствие массы',
            'formula': 'M1<=0 при t1>30°C',
            'result': 'Найдена ошибка',
            'status': 'error',
            'description': 'Масса равна 0 при температуре выше 30°C'
        })
    else:
        checks.append({
            'name': 'Отсутствие массы',
            'formula': 'M1<=0 при t1>30°C',
            'result': 'Ошибок не выявлено',
            'status': 'ok'
        })
    
    if Q_values:
        has_q_error = False
        for q in Q_values:
            if q is not None and q < 0:
                has_q_error = True
                break
        if has_q_error:
            checks.append({
                'name': 'Тепловая энергия Q >= 0',
                'formula': 'Q >= 0',
                'result': 'Найдена ошибка',
                'status': 'error',
                'description': 'Отрицательное значение тепловой энергии'
            })
        else:
            checks.append({
                'name': 'Тепловая энергия Q >= 0',
                'formula': 'Q >= 0',
                'result': 'Ошибок не выявлено',
                'status': 'ok'
            })
    
    # Проверка dt - ТОЛЬКО для heat (отопление), где есть обе температуры
    # Группируем по типу записи (type)
    heat_readings = [r for r in readings_table if r.get('type') == 'heat']
    if heat_readings:
        dt_errors = []
        for r in heat_readings:
            t1 = r.get('t1')
            t2 = r.get('t2')
            if t1 is not None and t2 is not None:
                dt = t1 - t2
                if dt < 2:
                    dt_errors.append({'date': r.get('timestamp', ''), 'dt': dt})
        
        if dt_errors:
            min_dt = min(e['dt'] for e in dt_errors)
            checks.append({
                'name': 'Разница температур dt >= 2°C',
                'formula': 't1 - t2 >= 2°C',
                'value': f'{min_dt:.1f}°C',
                'result': 'Найдена ошибка',
                'status': 'error',
                'description': f'Минимальная разница {min_dt:.1f}°C меньше 2°C ({len(dt_errors)} записей)'
            })
        else:
            dt_values = [(r.get('t1', 0) - r.get('t2', 0)) for r in heat_readings if r.get('t1') and r.get('t2')]
            min_dt = min(dt_values) if dt_values else 0
            checks.append({
                'name': 'Разница температур dt >= 2°C',
                'formula': 't1 - t2 >= 2°C',
                'value': f'{min_dt:.1f}°C',
                'result': 'Ошибок не выявлено',
                'status': 'ok'
            })
    
    if ns_values:
        has_ns = any(ns_values)
        if has_ns:
            ns_count = sum(1 for ns in ns_values if ns)
            checks.append({
                'name': 'Нештатные ситуации',
                'formula': 'ns = false',
                'value': f'{ns_count} записей с ns=true',
                'result': 'Найдена ошибка',
                'status': 'error',
                'description': f'Обнаружено {ns_count} нештатных ситуаций'
            })
        else:
            checks.append({
                'name': 'Нештатные ситуации',
                'formula': 'ns = false',
                'result': 'Ошибок не выявлено',
                'status': 'ok'
            })
    
    return checks

def sanitize_filename(filename):
    """Очистить имя файла от недопустимых символов"""
    import re
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    return filename

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5000)
