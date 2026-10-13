"""Independent, standard-library analysis of preserved historical measurements.
Does not certify the original handshake-success flags or measurement boundaries.
"""
import argparse
import csv
import json
import random
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'core'))
from policy_engine import select_group

METRICS = ['wire_latency_ms', 'handshake_latency_ms', 'cpu_time_ms', 'handshake_size_bytes', 'probe_cost_ms', 'policy_cost_ms']

def load(path):
    with path.open(newline='', encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))

def number(row, key):
    value = row.get(key, '')
    return float(value) if value != '' else None

def median(rows, key):
    values = [number(r, key) for r in rows if r.get(key, '') != '']
    return st.median(values) if values else None

def groups(rows, keys):
    out = defaultdict(list)
    for row in rows:
        out[tuple(row[k] for k in keys)].append(row)
    return out

def write_csv(path, rows):
    if not rows:
        return
    with path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

def percentile(values, q):
    values = sorted(values)
    position = (len(values) - 1) * q
    lo = int(position)
    hi = min(lo + 1, len(values) - 1)
    return values[lo] + (values[hi] - values[lo]) * (position - lo)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bootstrap', type=int, default=0, help='Independent resamples per matching-static comparison; 0 disables')
    parser.add_argument('--seed', type=int, default=20261013)
    parser.add_argument('--output', type=Path, default=ROOT / 'analysis' / 'generated')
    args = parser.parse_args()
    if args.bootstrap < 0 or 0 < args.bootstrap < 100:
        parser.error('--bootstrap must be 0 or at least 100')
    rows = load(ROOT / 'data/results.csv')
    crypto = load(ROOT / 'data/crypto_latency.csv')
    cells = groups(rows, ['enforced_profile', 'network_profile', 'config'])
    summary = []
    for key, cell in sorted(cells.items()):
        record = dict(zip(['device', 'network', 'config'], key))
        record.update(rows=len(cell), recorded_success=sum(r['success'].lower() == 'true' for r in cell))
        record.update({metric: median(cell, metric) for metric in METRICS})
        totals = [number(r, 'wire_latency_ms') + number(r, 'probe_cost_ms') for r in cell if r['probe_cost_ms']]
        record['first_connection_cost_ms'] = st.median(totals) if totals else None
        summary.append(record)
    savings, bootstrap = [], []
    rng = random.Random(args.seed)
    for (dev, net), condition in sorted(groups(rows, ['enforced_profile', 'network_profile']).items()):
        adaptive = cells[(dev, net, 'Adaptive')]
        baseline = cells[(dev, net, 'Static-1024')]
        record = {'device': dev, 'network': net}
        for metric in ['wire_latency_ms', 'cpu_time_ms', 'handshake_size_bytes']:
            a, b = median(adaptive, metric), median(baseline, metric)
            record[metric + '_saving_pct'] = 100 * (b - a) / b
        savings.append(record)
        if args.bootstrap:
            selected = adaptive[0]['requested_group']
            matching = [r for r in condition if r['config'] != 'Adaptive' and r['requested_group'] == selected]
            x = [float(r['wire_latency_ms']) for r in adaptive]
            y = [float(r['wire_latency_ms']) for r in matching]
            deltas = [st.median(rng.choices(x, k=len(x))) - st.median(rng.choices(y, k=len(y))) for _ in range(args.bootstrap)]
            bootstrap.append({'device': dev, 'network': net, 'matching_group': selected,
                              'median_difference_ms': st.median(x)-st.median(y),
                              'ci_low_ms': percentile(deltas, .025), 'ci_high_ms': percentile(deltas, .975),
                              'resamples': args.bootstrap, 'seed': args.seed})
    crypto_summary = []
    for key, cell in sorted(groups(crypto, ['device_profile', 'group']).items()):
        crypto_summary.append({'device': key[0], 'group': key[1], 'rows': len(cell),
                               **{metric: median(cell, metric) for metric in ['handshake_latency_ms', 'wire_latency_ms', 'handshake_size_bytes']}})
    adaptive = [r for r in rows if r['config'] == 'Adaptive']
    matches = sum(select_group({'rtt_ms': number(r, 'probed_rtt_ms'), 'cpu_share_pct': number(r, 'cpu_share_pct'), 'mem_limit_mb': number(r, 'mem_limit_mb')}).group == r['requested_group'] for r in adaptive)
    anomalies = []
    for group, cell in groups(rows, ['requested_group']).items():
        typical = st.mode(r['handshake_size_bytes'] for r in cell)
        anomalies.extend({k: r[k] for k in ['enforced_profile', 'network_profile', 'config', 'trial', 'handshake_size_bytes']} for r in cell if r['handshake_size_bytes'] != typical)
    validation = {'main_rows': len(rows), 'crypto_rows': len(crypto), 'main_cells': len(cells),
                  'main_cell_sizes': sorted(set(map(len, cells.values()))),
                  'recorded_main_success': sum(r['success'].lower() == 'true' for r in rows),
                  'recorded_crypto_success': sum(r['success'].lower() == 'true' for r in crypto),
                  'adaptive_rule_matches': matches, 'adaptive_rows': len(adaptive),
                  'byte_sum_matches': sum(int(r['handshake_size_bytes']) == int(r['handshake_c2s_bytes']) + int(r['handshake_s2c_bytes']) for r in rows),
                  'size_anomalies': anomalies,
                  'mean_condition_savings_pct': {k: st.mean(r[k] for r in savings) for k in savings[0] if k.endswith('_pct')},
                  'caveat': 'Historical recorded flags and measurements; known TLS success/timing defects are not resolved by this analysis.'}
    args.output.mkdir(parents=True, exist_ok=True)
    for name, data in [('summary.csv', summary), ('savings_vs_static1024.csv', savings), ('crypto_summary.csv', crypto_summary)]:
        write_csv(args.output / name, data)
    (args.output / 'validation.json').write_text(json.dumps(validation, indent=2) + '\n')
    if bootstrap:
        write_csv(args.output / 'matching_static_bootstrap.csv', bootstrap)
    else:
        (args.output / 'matching_static_bootstrap.csv').unlink(missing_ok=True)
    print(json.dumps(validation, indent=2))
    print('Summaries written to', args.output)

if __name__ == '__main__':
    main()
