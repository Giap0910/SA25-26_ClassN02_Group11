"""Sinh nghiệp vụ C từ stock_spec.json; giữ adapter nhị phân của mẫu C hiện có."""
import argparse
import ast
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_SPEC = HERE / 'stock_spec.json'
FIELDS = {'available', 'reserved', 'va', 'vr', 'state', 'variant'}
OPERATORS = {ast.Add: '+', ast.Sub: '-', ast.And: '&&', ast.Or: '||',
             ast.Lt: '<', ast.LtE: '<=', ast.Gt: '>', ast.GtE: '>=',
             ast.Eq: '==', ast.NotEq: '!='}


def expression(node):
    if isinstance(node, ast.Constant) and type(node.value) is int:
        if not -2147483648 <= node.value <= 2147483647:
            raise ValueError('Hằng số nằm ngoài int32')
        return f'INT64_C({node.value})'
    if isinstance(node, ast.Name) and node.id in FIELDS | {'q', 'restore'}:
        value = f's->{node.id}' if node.id in FIELDS else node.id
        return f'((int64_t){value})'
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return f'(!{expression(node.operand)})'
    if isinstance(node, ast.BinOp) and type(node.op) in (ast.Add, ast.Sub):
        return f'({expression(node.left)} {OPERATORS[type(node.op)]} {expression(node.right)})'
    if isinstance(node, ast.BoolOp) and type(node.op) in OPERATORS:
        return '(' + f' {OPERATORS[type(node.op)]} '.join(map(expression, node.values)) + ')'
    if isinstance(node, ast.Compare) and len(node.ops) == 1 and type(node.ops[0]) in OPERATORS:
        return f'({expression(node.left)} {OPERATORS[type(node.ops[0])]} {expression(node.comparators[0])})'
    raise ValueError('Biểu thức ngoài tập con an toàn được hỗ trợ')


def translate(text):
    if not isinstance(text, str) or len(text) > 500:
        raise ValueError('Biểu thức quá dài hoặc sai kiểu')
    node = ast.parse(text, mode='eval')
    if len(list(ast.walk(node))) > 80:
        raise ValueError('Biểu thức quá phức tạp')
    return expression(node.body)


def statement(rule):
    if 'return' in rule:
        if type(rule['return']) is not int or not 0 <= rule['return'] <= 7:
            raise ValueError('Mã kết quả không hợp lệ')
        code = f"return {rule['return']};"
    else:
        field = rule['set']
        if field not in FIELDS - {'variant'}:
            raise ValueError('Trường cập nhật không hợp lệ')
        value = translate(rule['value'])
        mode = rule.get('mode', 'assign')
        if mode not in ('assign', 'java_add'):
            raise ValueError('Chế độ cập nhật không hợp lệ')
        value = f'java_add(s->{field}, (int32_t){value})' if mode == 'java_add' else value
        code = f's->{field} = (int32_t)({value});'
    return f"    if ({translate(rule['when'])}) {{ {code} }}" if 'when' in rule else '    ' + code


def load_spec(path=DEFAULT_SPEC, check_backend=True):
    spec = json.loads(Path(path).read_text(encoding='utf-8'))
    if spec.get('version') != 1 or set(spec['operations']) != {'reserve', 'settle'}:
        raise ValueError('Phiên bản hoặc tập phép toán không được hỗ trợ')
    backend = HERE.parent / 'backend/src/main/java/com/sports/service'
    for name, expected in spec['backend_sha256'].items():
        if name not in ('OrderService.java', 'ProductVariantService.java'):
            raise ValueError('Tên service không hợp lệ')
        if check_backend and hashlib.sha256((backend / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f'Backend {name} đã đổi: cần đối chiếu lại đặc tả')
    for rules in spec['operations'].values():
        if not 1 <= len(rules) <= 50:
            raise ValueError('Số quy tắc không hợp lệ')
        for rule in rules:
            statement(rule)
    return spec


def generate(spec):
    adapter_path = HERE / 'reference_stock_simulator.c'
    adapter = (adapter_path if adapter_path.exists() else HERE / 'stock_simulator.c').read_text(encoding='utf-8')
    prefix = adapter[:adapter.index('static int reserve(')]
    suffix = adapter[adapter.index('static int simulate('):]
    functions = []
    for name, rules in spec['operations'].items():
        parameters = 'Stock *s, int32_t q' + (', int restore' if name == 'settle' else '')
        body = '\n'.join(statement(rule) for rule in rules)
        functions.append(f'static int {name}({parameters}) {{\n{body}\n    return 0;\n}}\n')
    digest = hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()
    return f'/* Generated from specification SHA256 {digest}. */\n' + prefix + '\n'.join(functions) + '\n' + suffix


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spec', type=Path, default=DEFAULT_SPEC)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    source = generate(load_spec(args.spec))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(source, encoding='utf-8')
    print(args.output)


if __name__ == '__main__':
    main()
