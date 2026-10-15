"""Kiểm thử API COD trên backend và database thử riêng, không gọi web đang chạy."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import re
import secrets
import socket
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
import zipfile
import xml.etree.ElementTree as ET

import fuzz_runner as runner
import generate_simulator as generator

JAVA = Path('C:/Program Files/Eclipse Adoptium/jdk-17.0.20.101-hotspot/bin/java.exe')
MAVEN = Path('C:/Program Files/Apache/apache-maven-3.9.16/bin/mvn.cmd')
MYSQL = Path('C:/xampp/mysql/bin/mysql.exe')
AGENT = Path('C:/Users/vxg09/.m2/repository/org/jacoco/org.jacoco.agent/0.8.12/org.jacoco.agent-0.8.12-runtime.jar')
BASE = 'http://127.0.0.1:18080'


def sql(schema, query):
    if schema and not re.fullmatch(r'fuzz_stock_[a-f0-9]{12}', schema):
        raise ValueError('Từ chối database ngoài phạm vi thử nghiệm')
    command = [str(MYSQL), '--no-defaults', '--host=127.0.0.1', '--port=3306',
               '--user=root', '--password=', '--batch', '--skip-column-names', '--default-character-set=utf8mb4']
    if schema:
        command.append(schema)
    process = subprocess.run(command, input=query, capture_output=True, text=True, encoding='utf-8', timeout=15)
    if process.returncode:
        raise RuntimeError('SQL trong môi trường thử thất bại: ' + process.stderr)
    return process.stdout.strip()


def http(method, path, data=None, token=None, key=None):
    if not path.startswith(('/api/auth/', '/api/orders')) or '..' in path:
        raise ValueError('Endpoint nằm ngoài phạm vi thử')
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    if key:
        headers['Idempotency-Key'] = key
    body = json.dumps(data, ensure_ascii=False).encode() if data is not None else None
    request = urllib.request.Request(BASE + path, body, headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        payload = error.read().decode('utf-8', errors='replace')
        return error.code, json.loads(payload) if payload.startswith('{') else {'message': payload}


def free_port():
    with socket.socket() as connection:
        connection.bind(('127.0.0.1', 0))
        return connection.getsockname()[1]


def build_backend(directory):
    jar = runner.ROOT / 'backend/target/web_badminton_backend-1.0.0.jar'
    libraries, classes = directory / 'lib', directory / 'classes'
    libraries.mkdir(); classes.mkdir()
    with zipfile.ZipFile(jar) as archive:
        for name in archive.namelist():
            if name.startswith('BOOT-INF/lib/') and name.endswith('.jar'):
                (libraries / Path(name).name).write_bytes(archive.read(name))
    backend = runner.ROOT / 'backend'
    lombok = Path('C:/Users/vxg09/.m2/repository/org/projectlombok/lombok/1.18.32/lombok-1.18.32.jar')
    sources = [str(path) for path in (backend / 'src/main/java').rglob('*.java')]
    command = [str(JAVA.with_name('javac.exe')), '-parameters', '-encoding', 'UTF-8', '--release', '17',
        '-cp', str(libraries / '*') + os.pathsep + str(lombok), '-processorpath', str(lombok),
        '-d', str(classes)] + sources
    process = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=90)
    (directory / 'build.log').write_text(process.stdout + process.stderr, encoding='utf-8')
    require(process.returncode == 0, 'Biên dịch backend thử thất bại; xem build.log')
    shutil.copytree(backend / 'src/main/resources', classes, dirs_exist_ok=True)
    return str(classes) + os.pathsep + str(libraries / '*')


def backend_properties(schema, directory):
    properties = {'spring.config.name': 'fuzz-isolated', 'spring.profiles.active': 'test',
        'server.address': '127.0.0.1', 'server.port': '18080', 'app.demo-data.enabled': 'false',
        'spring.datasource.url': f'jdbc:mysql://127.0.0.1:3306/{schema}?useSSL=false&serverTimezone=UTC',
        'spring.datasource.username': 'root', 'spring.datasource.password': '',
        'spring.jpa.hibernate.ddl-auto': 'update', 'spring.sql.init.mode': 'never',
        'payos.mode': 'REAL', 'payos.mock-enabled': 'false', 'payos.client-id': '',
        'payos.api-key': '', 'payos.checksum-key': '', 'payos.base-url': BASE + '/disabled-provider',
        'payos.return-url': BASE + '/unused', 'payos.cancel-url': BASE + '/unused',
        'app.product-images.storage-root': str(directory / 'images')}
    return properties


def start_backend(schema, directory, port, classpath):
    properties = backend_properties(schema, directory)
    environment = os.environ.copy()
    environment['APP_JWT_SECRET'] = secrets.token_hex(64)
    for key in ('JAVA_TOOL_OPTIONS', 'JDK_JAVA_OPTIONS', 'SPRING_APPLICATION_JSON',
                'SPRING_CONFIG_LOCATION', 'SPRING_CONFIG_ADDITIONAL_LOCATION', 'SPRING_CONFIG_IMPORT'):
        environment.pop(key, None)
    command = [str(JAVA), '-Dfile.encoding=UTF-8', f'-javaagent:{AGENT}=output=tcpserver,address=127.0.0.1,port={port},dumponexit=false',
               '-cp', classpath, 'com.sports.WebBadmintonApplication']
    command += [f'--{key}={value}' for key, value in properties.items()]
    log = (directory / 'backend.log').open('w', encoding='utf-8')
    process = subprocess.Popen(command, cwd=directory, env=environment, stdout=log, stderr=subprocess.STDOUT,
                               creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    return process, log


def await_backend(process):
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError('Backend thử dừng khi khởi động; xem backend.log')
        try:
            http('GET', '/api/auth/me')
            return
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            time.sleep(0.5)
    raise RuntimeError('Backend thử chưa sẵn sàng sau 90 giây')


def register(label):
    username = 'fuzz_' + label + '_' + uuid.uuid4().hex[:8]
    status, result = http('POST', '/api/auth/register', {'username': username,
        'email': username + '@example.invalid', 'password': secrets.token_hex(16),
        'fullName': 'Tài khoản kiểm thử', 'phone': '0900000000', 'address': 'Dữ liệu giả lập'})
    if status != 200 or not result.get('token'):
        raise AssertionError(f'Đăng ký tài khoản thử không đạt: {status} {result}')
    return result['token'], result['id']


def fixture(schema, available, reserved, variant):
    result = sql(schema, f"INSERT INTO products(name,brand,price,stock,reserved_stock,catalog_visible) "
        f"VALUES('Fuzz fixture','TEST',100000,{available},{reserved},1); SELECT LAST_INSERT_ID();")
    product = int(result)
    if variant:
        sql(schema, f"INSERT INTO product_variants(product_id,sku,stock,reserved_stock,active,legacy) "
            f"VALUES({product},'FUZZ-{product}',{available},{reserved},1,0);")
    return product


def stock(schema, product, variant):
    table = 'product_variants' if variant else 'products'
    predicate = 'product_id' if variant else 'id'
    return tuple(map(int, sql(schema, f'SELECT stock,reserved_stock FROM {table} WHERE {predicate}={product}').split('\t')))


def payload(product, quantity):
    return {'items': [{'productId': product, 'quantity': quantity}], 'customerName': 'Kiểm thử tồn kho',
        'shippingPhone': '0900000000', 'shippingAddress': 'Địa chỉ giả lập', 'paymentMethod': 'COD', 'shippingFee': 0}


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def verify_stock(schema, product, variant, expected):
    require(stock(schema, product, False) == expected, 'Sai tồn tổng')
    if variant:
        require(stock(schema, product, True) == expected, 'Sai tồn biến thể')


def finish_order(schema, product, variant, quantity, order, token, admin, action):
    if action == 1:
        method, path, actor = 'POST', f'/api/orders/{order}/cancel', token
    else:
        method, path, actor = 'PUT', f'/api/orders/{order}/status?status=SHIPPING', admin
    first = http(method, path, token=actor)
    require(first[0] == 200, f'Không kết thúc được đơn: {first}')
    before = stock(schema, product, variant)
    repeated = http(method, path, token=actor)
    require(repeated[0] == 200, f'Không xử lý được lặp: {repeated}')
    require(stock(schema, product, variant) == before, 'Thao tác lặp làm đổi kho')


def accepted_checks(schema, product, variant, quantity, body, key, result, actors):
    token, other, admin = actors
    order = result['id']
    before = stock(schema, product, variant)
    replay = http('POST', '/api/orders', body, token, key)
    require(replay[0] == 200 and replay[1].get('id') == order, 'Replay không trả cùng đơn')
    require(stock(schema, product, variant) == before, 'Replay trừ kho lần hai')
    changed = dict(body, note='Nội dung khác')
    conflict = http('POST', '/api/orders', changed, token, key)
    require(conflict[0] == 409, f'Không phát hiện xung đột khóa: {conflict}')
    denied = http('POST', f'/api/orders/{order}/cancel', token=other)
    require(denied[0] in (401, 403), f'Không chặn người khác hủy đơn: {denied}')
    require(stock(schema, product, variant) == before, 'Yêu cầu bị từ chối vẫn đổi kho')
    return order


def run_case(schema, binary, directory, actors, case):
    a, r, q, variant, action = case
    product = fixture(schema, a, r, variant)
    data = runner.pack(a, r, a, r, q, (8 if variant else 0) | action | 4)
    outcome, model, _ = runner.execute(binary, data, directory)
    require(outcome == 'ok', 'Simulator không khớp oracle')
    body, key = payload(product, q), str(uuid.uuid4())
    status, response = http('POST', '/api/orders', body, actors[0], key)
    accepted = model['status'] == 'accepted'
    require(status == 201 if accepted else status in (400, 409), f'HTTP không khớp C: {status} {response}')
    if accepted:
        order = accepted_checks(schema, product, variant, q, body, key, response, actors)
        finish_order(schema, product, variant, q, order, actors[0], actors[2], action)
    verify_stock(schema, product, variant, (model['available'], model['reserved']))
    return dict(initial_available=a, initial_reserved=r, quantity=q, variant=variant,
                action=action, http_status=status, model=model, outcome='pass', product_id=product)


def test_cases(iterations):
    fixed = [(10, 0, q, variant, action) for q in (-1, 0, 1, 10, 11, 100, 101)
             for variant in (False, True) for action in (1, 2)]
    fixed += [(100, runner.MAXIMUM, 1, True, 1), (0, 0, 1, True, 1)]
    for seed in (1, 7, 42):
        rng = random.Random(seed)
        fixed += [(rng.choice([0, 1, 10, 100]), 0, rng.choice([-1, 0, 1, 2, 99, 100, 101]),
                   bool(rng.randrange(2)), rng.choice([1, 2])) for _ in range(iterations)]
    return fixed


def malformed_cases(schema, actors):
    product = fixture(schema, 10, 0, False)
    cases = [('missing-jwt', payload(product, 1), None, str(uuid.uuid4()), (401, 403)),
             ('invalid-key', payload(product, 1), actors[0], 'not-a-uuid', (400,)),
             ('missing-key', payload(product, 1), actors[0], None, (400,))]
    for index, quantity in enumerate((None, 1.5, 'invalid', 2147483648)):
        cases.append((f'quantity-type-{index}', payload(product, quantity), actors[0], str(uuid.uuid4()), (400,)))
    cases.append(('empty-items', dict(payload(product, 1), items=[]), actors[0], str(uuid.uuid4()), (400,)))
    results = []
    for name, body, actor, key, expected in cases:
        status, _ = http('POST', '/api/orders', body, actor, key)
        require(status in expected, f'Kiểm tra {name} không đạt: HTTP {status}')
        verify_stock(schema, product, False, (10, 0))
        results.append({'case': name, 'http_status': status, 'stock_unchanged': True})
    return results


def dump_coverage(directory, port):
    command = [str(MAVEN), '-o', 'org.jacoco:jacoco-maven-plugin:0.8.12:dump',
        '-Djacoco.address=127.0.0.1', f'-Djacoco.port={port}',
        f'-Djacoco.destFile={directory / "api.exec"}', '-Djacoco.append=false', '-Djacoco.retryCount=1']
    process = subprocess.run(command, cwd=runner.ROOT / 'backend', capture_output=True, text=True, timeout=60)
    (directory / 'jacoco-dump.log').write_text(process.stdout + process.stderr, encoding='utf-8')
    require(process.returncode == 0 and (directory / 'api.exec').stat().st_size > 0, 'Chưa thu được JaCoCo API')


def coverage_script(directory):
    quote = lambda path: json.dumps(str(path).replace('\\', '/'))
    source = runner.ROOT / 'backend/src/main/java'
    lines = ['import java.io.*;', 'import java.util.*;', 'import org.jacoco.core.tools.*;',
        'import org.jacoco.core.analysis.*;', 'import org.jacoco.report.*;',
        'import org.jacoco.report.html.*;', 'import org.jacoco.report.xml.*;',
        'ExecFileLoader loader = new ExecFileLoader();', f'loader.load(new File({quote(directory / "api.exec")}));',
        'CoverageBuilder builder = new CoverageBuilder();',
        'Analyzer analyzer = new Analyzer(loader.getExecutionDataStore(), builder);']
    for name in ('OrderService', 'ProductVariantService'):
        path = directory / 'classes/com/sports/service' / (name + '.class')
        lines.append(f'analyzer.analyzeAll(new File({quote(path)}));')
    lines += [f'var xml = new XMLFormatter().createVisitor(new FileOutputStream({quote(directory / "coverage.xml")}));',
        f'var html = new HTMLFormatter().createVisitor(new FileMultiReportOutput(new File({quote(directory / "coverage-html")})));',
        'var visitor = new MultiReportVisitor(Arrays.asList(xml, html));',
        'visitor.visitInfo(loader.getSessionInfoStore().getInfos(), loader.getExecutionDataStore().getContents());',
        f'visitor.visitBundle(builder.getBundle("Kiểm thử API tồn kho tách biệt"), new DirectorySourceFileLocator(new File({quote(source)}), "UTF-8", 4));',
        'visitor.visitEnd();', '/exit']
    return '\n'.join(lines) + '\n'


def report_coverage(directory):
    repository = Path('C:/Users/vxg09/.m2/repository')
    jars = [repository / f'org/jacoco/org.jacoco.{name}/0.8.12/org.jacoco.{name}-0.8.12.jar' for name in ('core', 'report')]
    jars += [repository / f'org/ow2/asm/{name}/9.7/{name}-9.7.jar' for name in ('asm', 'asm-tree', 'asm-commons')]
    command = [str(JAVA.with_name('jshell.exe')), '--class-path', os.pathsep.join(map(str, jars)), '--feedback', 'concise']
    process = subprocess.run(command, input=coverage_script(directory), capture_output=True, text=True,
                             encoding='utf-8', errors='replace', timeout=90)
    (directory / 'jacoco-report.log').write_text(process.stdout + process.stderr, encoding='utf-8')
    require((directory / 'coverage.xml').exists(), 'Chưa xuất được báo cáo coverage.xml')
    root = ET.parse(directory / 'coverage.xml').getroot()
    results = {item.attrib['name']: {c.attrib['type']: dict(covered=int(c.attrib['covered']), missed=int(c.attrib['missed']))
               for c in item.findall('counter')} for item in root.findall('./package/class')}
    require(len(results) == 2 and all(item['INSTRUCTION']['covered'] > 0 for item in results.values()), 'Coverage chưa khớp hai service')
    return results


def prepare_run(args):
    generator.load_spec()
    require(args.simulator.is_file(), 'Không tìm thấy binary C đã kiểm tra')
    metadata = json.loads((args.simulator.parent.parent / 'metadata.json').read_text(encoding='utf-8'))
    require(metadata['spec_sha256'] == hashlib.sha256(generator.DEFAULT_SPEC.read_bytes()).hexdigest(), 'Binary C thuộc đặc tả cũ')
    os.environ['PATH'] = str(runner.OUTPUT / 'toolchain/mingw64/bin') + os.pathsep + os.environ.get('PATH', '')
    with socket.socket() as connection:
        require(connection.connect_ex(('127.0.0.1', 18080)) != 0, 'Cổng 18080 đang được dùng; không can thiệp')
    schema = 'fuzz_stock_' + uuid.uuid4().hex[:12]
    directory = runner.OUTPUT / ('api-' + schema)
    directory.mkdir()
    sql(None, f'CREATE DATABASE `{schema}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;')
    report = {'schema': schema, 'base_url': BASE, 'seed': [1, 7, 42], 'results': [], 'status': 'incomplete',
              'backend': metadata['backend'], 'simulator_sha256': hashlib.sha256(args.simulator.read_bytes()).hexdigest(),
              'synthetic_fixtures': 'Có fixture INT_MAX do test chèn trực tiếp; không khẳng định API quản trị tạo được.',
              'claim': 'HTTP fuzz theo biên, đối chiếu C và kho DB; không phải coverage-guided HTTP; không test PayOS.'}
    return schema, directory, report


def test_actors(schema):
    token, _ = register('owner')
    other, _ = register('other')
    admin_token, admin_id = register('admin')
    sql(schema, f"UPDATE users SET role='ROLE_ADMIN' WHERE id={admin_id};")
    return token, other, admin_token


def campaign(args, schema, directory, report):
    actors = test_actors(schema)
    report['validation_checks'] = malformed_cases(schema, actors)
    for case in test_cases(args.iterations):
        report['current_case'] = case
        report['results'].append(run_case(schema, args.simulator, directory, actors, case))
    report.pop('current_case', None)


def run(args):
    schema, directory, report = prepare_run(args)
    classpath = build_backend(directory)
    port = free_port()
    process, log = start_backend(schema, directory, port, classpath)
    try:
        await_backend(process)
        campaign(args, schema, directory, report)
        dump_coverage(directory, port)
        report['coverage'] = report_coverage(directory)
        report['status'] = 'pass'
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        process.terminate(); process.wait(timeout=15); log.close()
        (directory / 'summary.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(directory)
    print(f"PASS: {len(report['results'])} ca API; database thử được giữ nguyên: {schema}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-isolated', action='store_true', required=True)
    parser.add_argument('--simulator', type=Path, required=True)
    parser.add_argument('--iterations', type=int, default=20)
    args = parser.parse_args()
    require(1 <= args.iterations <= 100, 'Ngân sách mỗi seed phải từ 1 đến 100')
    run(args)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    main()
