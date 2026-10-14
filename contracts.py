"""Independent numeric contracts extracted from the qualified PicoGK course."""
from decimal import Decimal, InvalidOperation
import json
import math
import re

LANGUAGES = ('en', 'fr', 'de', 'ja', 'zh')
FIELDS = {
    'cylinder': [('length', 'length'), ('outer', 'radius')],
    'pipe': [('length', 'length'), ('outer', 'radius'), ('inner', 'radius')],
    'washer': [('thickness', 'length'), ('outer', 'radius'), ('bore', 'radius')],
    'bcc': [('cell_side', 'length'), ('beam', 'diameter')],
    'thread': [('length', 'length'), ('outer', 'radius'), ('core', 'radius'), ('pitch', 'length')],
}
UNITS = {'mm': Decimal(1), 'cm': Decimal(10), 'm': Decimal(1000)}


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key')
        result[key] = value
    return result


def parse(text):
    value = json.loads(text, object_pairs_hook=unique)
    if not isinstance(value, dict) or set(value) != {'recipe', 'parameters_mm', 'missing'}:
        raise ValueError('Plan schema')
    recipe, params, missing = value['recipe'], value['parameters_mm'], value['missing']
    if type(recipe) is not str or recipe not in (*FIELDS, 'needs_measurement') or not isinstance(params, list) or not isinstance(missing, list):
        raise ValueError('Plan types')
    if recipe == 'needs_measurement':
        if params or missing != ['measured_interfaces']:
            raise ValueError('Missing-interface contract')
        return value
    if missing or len(params) != len(FIELDS[recipe]):
        raise ValueError('Parameter count')
    if any(type(v) not in (int, float) or not math.isfinite(v) or not 0.5 <= v <= 24 for v in params):
        raise ValueError('Numeric bounds')
    if recipe in ('pipe', 'washer') and params[2] >= params[1]:
        raise ValueError('Bore must be smaller')
    if recipe == 'bcc' and (params[1] > params[0]/3 or params[0] > 18):
        raise ValueError('Lattice bounds')
    if recipe == 'thread' and (params[2] >= params[1] or params[3] < 2 or params[0]/params[3] > 6):
        raise ValueError('Thread bounds')
    return value


def normalize(request):
    if not isinstance(request, dict) or set(request) != {'recipe', 'language', 'interface_status', 'fields'}:
        raise ValueError('Request requires recipe, language, interface_status and fields')
    if any(type(request[key]) is not str for key in ('recipe', 'language', 'interface_status')):
        raise ValueError('Recipe, language and interface status must be strings')
    language, status, fields = request['language'], request['interface_status'], request['fields']
    if language not in LANGUAGES or status not in ('synthetic', 'missing', 'unverified') or not isinstance(fields, dict):
        raise ValueError('Unsupported language, interface status or fields')
    if status != 'synthetic':
        return {'recipe': 'needs_measurement', 'parameters_mm': [], 'missing': ['measured_interfaces']}
    recipe = request['recipe']
    if recipe not in FIELDS or set(fields) != {name for name, _ in FIELDS[recipe]}:
        raise ValueError('Provide every named recipe field without extras')
    values = []
    for name, target in FIELDS[recipe]:
        field = fields[name]
        if not isinstance(field, dict) or set(field) != {'value', 'unit', 'quantity'}:
            raise ValueError('Each field requires value, unit and quantity')
        if type(field['unit']) is not str or field['unit'] not in UNITS or type(field['value']) not in (str, int, float):
            raise ValueError('Unsupported unit or value')
        text = str(field['value']).strip()
        pattern = r'[0-9]+(?:[.,][0-9]+)?' if language in ('fr', 'de') else r'[0-9]+(?:\.[0-9]+)?'
        if len(text) > 64 or not re.fullmatch(pattern, text):
            raise ValueError('Use an explicit decimal without grouping or inferred units')
        try:
            number = Decimal(text.replace(',', '.')) * UNITS[field['unit']]
        except InvalidOperation as error:
            raise ValueError('Invalid decimal') from error
        quantity = field['quantity']
        if type(quantity) is not str:
            raise ValueError('Quantity must be a string')
        if target == 'length':
            if quantity != 'length':
                raise ValueError('Length field has a radial quantity')
        elif quantity not in ('radius', 'diameter'):
            raise ValueError('Specify radius or diameter explicitly')
        elif target != quantity:
            number = number / 2 if target == 'radius' else number * 2
        if not number.is_finite():
            raise ValueError('Nonfinite quantity')
        values.append(float(number))
    return parse(json.dumps({'recipe': recipe, 'parameters_mm': values, 'missing': []}, allow_nan=False))


def canonical(request):
    plan = normalize(request)
    if plan['recipe'] == 'needs_measurement':
        return 'Original Porsche mounting interfaces are missing or unverified. Return needs_measurement; invent no dimensions.'
    names = ', '.join(name for name, _ in FIELDS[plan['recipe']])
    return (f"Synthetic {plan['recipe']}. Named fields in order: {names}. "
            f"parameters_mm={json.dumps(plan['parameters_mm'], separators=(',', ':'))}. "
            'These values already use the ordered recipe quantities in millimeters. Preserve them exactly; do not halve radii.')


def matches(actual, expected):
    return (actual['recipe'] == expected['recipe'] and actual['missing'] == expected['missing'] and
            len(actual['parameters_mm']) == len(expected['parameters_mm']) and
            all(math.isclose(a, b, rel_tol=0, abs_tol=1e-6) for a, b in zip(actual['parameters_mm'], expected['parameters_mm'])))


def accepted(text, finish, request):
    if finish != 'stop':
        raise ValueError('Response did not reach EOS')
    plan = parse(text)
    if not matches(plan, normalize(request)):
        raise ValueError('Model proposal differs from the independent request contract')
    return plan
