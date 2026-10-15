"""Fuzzer C: tùy chỉnh nguyên lý ATPM ch4_dynamic, không gọi website/database."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import struct
import subprocess
import sys
import time
import uuid
import generate_simulator

ROOT = Path(__file__).resolve().parent.parent
SOURCE = Path(__file__).with_name('stock_simulator.c')
OUTPUT = ROOT / 'backend' / 'target' / 'software-security-fuzz'
BACKEND = ROOT / 'backend' / 'src' / 'main' / 'java' / 'com' / 'sports' / 'service'
MAXIMUM = 2147483647
BOUNDARIES = [0, 1, 2, 99, 100, 101, MAXIMUM-100, MAXIMUM-1, MAXIMUM]


def pack(available, reserved, va, vr, quantity, action):
    return b'BDMN' + struct.pack('<iiiiiI', available, reserved, va, vr, quantity, action)


def oracle(data):
    if len(data) != 28:
        return 'invalid_length', None
    for i, expected in enumerate(b'BDMN'):
        if data[i] != expected:
            return f'header_{i}', None
    a, r, va, vr, q, action = struct.unpack('<iiiiiI', data[4:])
    variant = bool(action & 8)
    if a < 0 or r < 0 or variant and (va < 0 or vr < 0 or a != va or r != vr):
        return 'invalid_fixture', None
    if not 1 <= q <= 100 or a < q or r + q > MAXIMUM:
        return 'rejected', (a, r, va, vr, 0)
    if variant and (va < q or vr + q > MAXIMUM):
        return 'rejected', (a, r, va, vr, 0)
    state = 1
    a, r = a - q, r + q
    if variant:
        va, vr = va - q, vr + q
    if action & 3:
        restore = action & 3 == 1
        a, r = a + (q if restore else 0), r - q
        if variant:
            va, vr = va + (q if restore else 0), vr - q
        state = 2 if restore else 3
    return 'accepted', (a, r, va, vr, state)


def execute(binary, data, directory):
    path = directory / ('input-'+uuid.uuid4().hex+'.bin')
    path.write_bytes(data)
    try:
        p = subprocess.run([str(binary), str(path)], cwd=directory, capture_output=True,
                           timeout=2, text=True, encoding='utf-8', errors='replace')
    except subprocess.TimeoutExpired:
        return 'timeout', {}, ''
    if p.returncode == 10:
        return 'invariant_failure', {}, p.stdout + p.stderr
    if p.returncode < 0 or p.returncode >= 0x80000000:
        return 'crash', {}, p.stdout + p.stderr
    if p.returncode:
        raise RuntimeError(f'Target lỗi môi trường, mã {p.returncode}: {p.stderr}')
    result = json.loads(p.stdout)
    status, values = oracle(data)
    if result['status'] != status:
        return 'oracle_mismatch', result, p.stdout
    if values is not None:
        actual = tuple(result[k] for k in ('available', 'reserved', 'variant_available',
                                         'variant_reserved', 'state'))
        if actual != values:
            return 'oracle_mismatch', result, p.stdout
    return 'ok', result, p.stdout


def gcov_output(directory, gcov):
    p = subprocess.run([gcov, '-b', '-c', 'stock_simulator.c'], cwd=directory,
                       capture_output=True, text=True)
    if p.returncode:
        raise RuntimeError(f'gcov không đo được coverage: {p.stdout} {p.stderr}')
    return (directory / 'stock_simulator.c.gcov').read_text(encoding='utf-8', errors='replace')


def coverage(directory, gcov):
    lines, branches, total_lines, total_branches = set(), set(), set(), set()
    line, branch_index = 0, 0
    for text in gcov_output(directory, gcov).splitlines():
        fields = text.split(':', 2)
        if len(fields) == 3:
            count, number = fields[0].strip(), fields[1].strip()
            if number.isdigit():
                line, branch_index = int(number), 0
                if line and count != '-':
                    total_lines.add(line)
                    if count.rstrip('*').isdigit() and int(count.rstrip('*')) > 0:
                        lines.add(line)
        if text.strip().startswith('branch '):
            tokens = text.split()
            key = (line, branch_index)
            total_branches.add(key)
            if 'taken' in tokens and int(tokens[tokens.index('taken')+1]) > 0:
                branches.add(key)
            branch_index += 1
    if not total_lines:
        raise RuntimeError('gcov không cung cấp dữ liệu dòng thực thi')
    return lines, branches, total_lines, total_branches


def compile_target(directory, gcc, source=None):
    shutil.copyfile(source or SOURCE, directory / SOURCE.name)
    binary = directory / ('stock_simulator.exe' if os.name == 'nt' else 'stock_simulator')
    command = [gcc, '-std=c11', '-Wall', '-Wextra', '-Werror', '-O0', '--coverage',
               '-c', 'stock_simulator.c', '-o', 'stock_simulator.o']
    p = subprocess.run(command, cwd=directory, capture_output=True, text=True)
    if p.returncode == 0:
        p = subprocess.run([gcc, '--coverage', 'stock_simulator.o', '-o', str(binary)],
                           cwd=directory, capture_output=True, text=True)
    (directory / 'compile.log').write_text(p.stdout+p.stderr, encoding='utf-8')
    if p.returncode:
        raise RuntimeError(f'Biên dịch thất bại: {p.stderr}')
    return binary


def mutation(rng, corpus):
    data = bytearray(rng.choice(corpus))
    index = rng.randrange(len(data))
    data[index] = rng.randrange(256)
    return bytes(data)


def candidate(rng, corpus, mode, input_mode):
    if input_mode == 'raw':
        return bytes(rng.randrange(256) for _ in range(28)) if mode == 'black-box' else mutation(rng, corpus)
    if mode == 'black-box':
        a, r, q = [rng.choice(BOUNDARIES) for _ in range(3)]
        return pack(a, r, a, r, q, rng.randrange(16))
    a, r, _, _, q, action = struct.unpack('<iiiiiI', rng.choice(corpus)[4:])
    fields = [a, r, q, action]
    index = rng.randrange(4)
    fields[index] = rng.randrange(16) if index == 3 else rng.choice(BOUNDARIES)
    a, r, q, action = fields
    return pack(a, r, a, r, q, action)


def record_outcome(directory, counts, outcome, i, data, log):
    if outcome == 'ok':
        return
    counts[outcome] += 1
    stem = f'{outcome}-{i}'
    (directory / (stem+'.bin')).write_bytes(data)
    (directory / (stem+'.txt')).write_text(log, encoding='utf-8')


def record_target(directory, result, i, data, start, first):
    if first is not None or result.get('status') != 'accepted' or result.get('state') != 2:
        return first
    (directory / 'target-input.bin').write_bytes(data)
    return {'iteration': i, 'seconds': time.perf_counter()-start}


def campaign_state(seed, input_mode):
    counts = {k: 0 for k in ('crash', 'timeout', 'invariant_failure', 'oracle_mismatch')}
    initial = bytes(28) if input_mode == 'raw' else pack(0, 0, 0, 0, 0, 0)
    return random.Random(seed), [initial], set(), set(), counts, None, set(), set(), time.perf_counter(), 0


def campaign(binary, directory, gcov, mode, seed, budget, seconds, input_mode):
    rng, corpus, seen_lines, seen_branches, counts, first_target, all_lines, all_branches, start, used = campaign_state(seed, input_mode)
    with (directory / 'events.csv').open('w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow(['iteration', 'elapsed_seconds', 'outcome', 'status', 'lines', 'branches'])
        for i in range(1, budget+1):
            if time.perf_counter() - start >= seconds:
                break
            data = candidate(rng, corpus, mode, input_mode)
            outcome, result, log = execute(binary, data, directory)
            lines, branches, all_lines, all_branches = coverage(directory, gcov)
            novel = bool(lines-seen_lines or branches-seen_branches)
            seen_lines.update(lines); seen_branches.update(branches)
            if mode != 'black-box' and novel:
                corpus.append(data)
            first_target = record_target(directory, result, i, data, start, first_target)
            record_outcome(directory, counts, outcome, i, data, log)
            used = i
            writer.writerow([i, round(time.perf_counter()-start, 6), outcome,
                             result.get('status'), len(seen_lines), len(seen_branches)])
            if outcome != 'ok':
                break
    return dict(mode=mode, input_mode=input_mode, seed=seed, iterations=used, seconds=time.perf_counter()-start,
                first_target=first_target, line_hits=len(seen_lines), line_total=len(all_lines),
                branch_hits=len(seen_branches), branch_total=len(all_branches), corpus=len(corpus), **counts)


def regressions(binary, directory):
    cases = [pack(10, 0, 10, 0, 2, action) for action in (0, 1, 2, 5, 6, 8, 9, 10, 13, 14)]
    cases += [pack(10, 0, 10, 0, q, 8) for q in (-1, 0, 1, 100, 101)]
    cases += [pack(a, r, a, r, q, 8) for a, r, q in
              [(1,0,1), (0,0,1), (100,MAXIMUM,1), (100,MAXIMUM-100,100),
               (100,MAXIMUM-99,100), (100,0,100)]]
    cases += [b'', b'BDMN', bytes(28), pack(-1,0,0,0,1,0)]
    results = []
    for index, data in enumerate(cases, 1):
        outcome, result, log = execute(binary, data, directory)
        results.append(dict(case=index, input=data.hex(), outcome=outcome, result=result, log=log))
    (directory / 'regression.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    if any(r['outcome'] != 'ok' for r in results):
        raise RuntimeError('Có ca hồi quy không đạt; xem regression.json')
    return len(results)


def record_metadata(destination, gcc, gcov, args):
    metadata = {'source_sha256': hashlib.sha256((destination/SOURCE.name).read_bytes()).hexdigest(), 'backend': {},
                'spec_sha256': hashlib.sha256(generate_simulator.DEFAULT_SPEC.read_bytes()).hexdigest(),
                'generator_sha256': hashlib.sha256(Path(generate_simulator.__file__).read_bytes()).hexdigest(),
                'adapter_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
                'runner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                'budget': {'iterations': args.iterations, 'seconds': args.seconds,
                           'seeds': args.seeds, 'input_mode': args.input_mode},
                'gcc': subprocess.check_output([gcc, '--version'], text=True).splitlines()[0],
                'gcov': subprocess.check_output([gcov, '--version'], text=True).splitlines()[0]}
    for name in ('OrderService.java', 'ProductVariantService.java'):
        metadata['backend'][name] = hashlib.sha256((BACKEND/name).read_bytes()).hexdigest()
    (destination/'metadata.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')


def prepare_run(args):
    gcc, gcov = shutil.which(args.gcc), shutil.which(args.gcov)
    if not gcc or not gcov:
        raise RuntimeError('Cần GCC và gcov cùng bộ phiên bản trên PATH; chưa chạy C/fuzz/coverage.')
    os.environ['PATH'] = str(Path(gcc).parent) + os.pathsep + os.environ.get('PATH', '')
    destination = OUTPUT / (time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8])
    destination.mkdir(parents=True)
    source = destination / SOURCE.name
    source.write_text(generate_simulator.generate(generate_simulator.load_spec()), encoding='utf-8')
    for path in (generate_simulator.DEFAULT_SPEC, Path(generate_simulator.__file__), Path(__file__)):
        shutil.copyfile(path, destination / path.name)
    shutil.copyfile(SOURCE, destination / 'reference_stock_simulator.c')
    record_metadata(destination, gcc, gcov, args)
    return gcc, gcov, destination, source


def run(args):
    gcc, gcov, destination, source = prepare_run(args)
    regression_dir = destination/'regression'; regression_dir.mkdir()
    binary = compile_target(regression_dir, gcc, source)
    count = regressions(binary, regression_dir)
    summaries = []
    for seed in args.seeds:
        for mode in ('black-box', 'coverage-guided'):
            directory = destination/f'{mode}-{seed}'; directory.mkdir()
            binary = compile_target(directory, gcc, source)
            summaries.append(campaign(binary, directory, gcov, mode, seed, args.iterations, args.seconds, args.input_mode))
    report = dict(regressions=count, results=summaries, claim='Kết quả C simulator; không phải kiểm thử HTTP/DB/PayOS.')
    (destination/'summary.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    with (destination/'summary.csv').open('w', newline='', encoding='utf-8-sig') as file:
        writer = csv.DictWriter(file, fieldnames=summaries[0].keys()); writer.writeheader(); writer.writerows(summaries)
    print(json.dumps(report, ensure_ascii=False, indent=2)); print(destination)
    return 1 if any(any(r[k] for k in ('crash', 'timeout', 'invariant_failure', 'oracle_mismatch')) for r in summaries) else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    portable = OUTPUT / 'toolchain' / 'mingw64' / 'bin'
    parser.add_argument('--gcc', default=str(portable/'gcc.exe') if (portable/'gcc.exe').exists() else 'gcc')
    parser.add_argument('--gcov', default=str(portable/'gcov.exe') if (portable/'gcov.exe').exists() else 'gcov')
    parser.add_argument('--iterations', type=int, default=2000)
    parser.add_argument('--seconds', type=float, default=30)
    parser.add_argument('--seeds', nargs='+', type=int, default=[1, 7, 42])
    parser.add_argument('--print-spec', action='store_true')
    parser.add_argument('--input-mode', choices=['raw', 'structured'], default='structured')
    args = parser.parse_args()
    if args.print_spec:
        print(json.dumps(spec_tables(), ensure_ascii=False)); return 0
    if args.iterations <= 0 or args.seconds <= 0:
        parser.error('iterations và seconds phải dương')
    try:
        return run(args)
    except (RuntimeError, OSError, ValueError) as error:
        print(f'CHƯA HOÀN TẤT: {error}', file=sys.stderr); return 2




def spec_tables():
    return generate_simulator.load_spec()['teacher_tables']


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    raise SystemExit(main())
