"""Explicit unsigned semantics shared by emitters, not their implementations."""
import copy
import hashlib
import json
import random

MASK = 0xffffffff
OPS = ('add', 'sub', 'mul', 'xor', 'and', 'or', 'shl', 'shr')


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'))


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def validate(case):
    if not isinstance(case, dict) or case.get('schema') != 1:
        raise ValueError('Case must have schema 1')
    if case.get('kind', 'map') not in ('map', 'reduce'):
        raise ValueError('Unsupported kernel kind')
    inputs, ops = case.get('inputs'), case.get('ops')
    if not isinstance(inputs, list) or not 1 <= len(inputs) <= 4096:
        raise ValueError('Expected 1..4096 inputs')
    if not isinstance(ops, list) or len(ops) > 256:
        raise ValueError('Expected at most 256 operations')
    for x in inputs:
        if type(x) is not int or not 0 <= x <= MASK:
            raise ValueError('Input outside uint32')
    for pair in ops:
        if not isinstance(pair, list) or len(pair) != 2:
            raise ValueError('Operation must be [opcode, constant]')
        op, k = pair
        if op not in OPS or type(k) is not int or not 0 <= k <= (31 if op in ('shl', 'shr') else MASK):
            raise ValueError('Invalid operation or constant')
    return case


def generate(seed, count=12, kind='map'):
    if type(count) is not int or not 0 <= count <= 256:
        raise ValueError('Operation count outside 0..256')
    rng = random.Random(seed)
    ops = []
    for _ in range(count):
        op = rng.choice(OPS)
        edge = [0, 1, 31] if op in ('shl', 'shr') else [0, 1, MASK, 0x80000000, 0x7fffffff]
        k = rng.choice(edge) if rng.random() < .4 else rng.randrange(32 if op in ('shl', 'shr') else MASK + 1)
        ops.append([op, k])
    return validate({'schema': 1, 'kind': kind, 'seed': seed, 'ops': ops,
                     'inputs': [0, 1, MASK, 0x80000000, 0x7fffffff] + [rng.getrandbits(32) for _ in range(28)]})


def reference(case):
    validate(case)
    values = []
    for x in case['inputs']:
        for op, k in case['ops']:
            if op == 'add': x += k
            elif op == 'sub': x -= k
            elif op == 'mul': x *= k
            elif op == 'xor': x ^= k
            elif op == 'and': x &= k
            elif op == 'or': x |= k
            elif op == 'shl': x <<= k
            elif op == 'shr': x >>= k
            x &= MASK
        values.append(x)
    return [sum(values) & MASK] if case.get('kind') == 'reduce' else values


def transform(case, name):
    result = copy.deepcopy(validate(case))
    additions = {'identity': [['add', 0], ['xor', 0]],
                 'xor-pair': [['xor', 0xa5a5a5a5], ['xor', 0xa5a5a5a5]],
                 'inverse-add': [['add', MASK], ['sub', MASK]]}
    if name not in additions:
        raise ValueError('Unknown transformation')
    result['ops'] += additions[name]
    result['metamorphic'] = name
    return validate(result)


def boundary_cases():
    for op, k in [('add', 1), ('sub', 1), ('mul', 2), ('shl', 31), ('shr', 1), ('shr', 31), ('xor', MASK), ('and', 0), ('or', MASK)]:
        yield {'schema': 1, 'kind': 'map', 'seed': f'boundary-{op}-{k}', 'ops': [[op, k]],
               'inputs': [0, 1, MASK, 0x80000000, 0x7fffffff]}


def fault_case():
    return {'schema': 1, 'kind': 'map', 'seed': 'synthetic-shift-fault',
            'ops': [['add', 0], ['shr', 1], ['xor', 0]], 'inputs': [0, 1, 0x80000000, MASK]}
