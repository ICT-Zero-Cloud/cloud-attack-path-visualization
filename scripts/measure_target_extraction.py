"""Compare L0/L3 target extraction against fixed investigation resource evidence.

Does not run an investigation query or modify existing scenario CSVs.
"""
import csv
import os
import hashlib
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results/target_extraction'
# 원본 CloudTrail 로그 위치 (저장소에 포함하지 않음). 환경변수 CT_RAW_DIR로 바꿀 수 있다.
RAW_DIR = Path(os.environ.get('CT_RAW_DIR', ROOT / 'data/raw'))
if not all((RAW_DIR / f'aws.5_chain_n{i}.json').exists() for i in range(1, 5)):
    sys.exit(f'원본 로그가 없습니다: {RAW_DIR}/aws.5_chain_n1~n4.json (data/raw/README.md 참고)')


def read_csv(path):
    with path.open(encoding='utf-8', newline='') as stream:
        return list(csv.DictReader(stream))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    frozen = []
    # Freeze every case before parsing either variant. Reuse prior required GT;
    # exclude credential issuance and generic service endpoints, not missing hits.
    for i in range(1, 5):
        gt_path = ROOT / f'groundtruth_json/aws.5_chain_n{i}.common.json'
        gt = json.loads(gt_path.read_text(encoding='utf-8'))
        raw_path = RAW_DIR / f'aws.5_chain_n{i}.json'
        raw = {r['eventID']: r for r in json.loads(raw_path.read_text(encoding='utf-8'))['Records']}
        access = sorted({(src, dst, eid) for rel, src, dst, eid in gt['required_connections']
                         if rel != 'OBTAINS' and dst.startswith('arn:aws:')})
        for src, dst, eid in access:
            assert eid in raw, (i, eid)
            assert raw[eid]['userIdentity'].get('accessKeyId') == src, (i, eid, src)
        frozen.append(dict(scenario=f'n{i}', source_gt=str(gt_path.relative_to(ROOT)),
                           source_gt_sha256=digest(gt_path), raw_sha256=digest(raw_path),
                           targets=sorted({dst for _, dst, _ in access}), accesses=access))
    (OUT / 'fixed_groundtruth.json').write_text(json.dumps(frozen, ensure_ascii=False, indent=2), encoding='utf-8')
    results = []
    for case in frozen:
        name = case['scenario']
        raw_path = RAW_DIR / f'aws.5_chain_{name}.json'
        record = dict(scenario=name, required_targets=len(case['targets']),
                      required_accesses=len(case['accesses']), levels={})
        for level in (0, 3):
            directory = OUT / f'{name}_L{level}'
            proc = subprocess.run([sys.executable, '-X', 'utf8', str(ROOT / 'parser_node3_v2.py'),
                                   str(raw_path), '-o', str(directory), '--extract-level', str(level)],
                                  check=True, capture_output=True, encoding='utf-8')
            (directory / 'parser_output.txt').write_text(proc.stdout, encoding='utf-8')
            nodes = {r['id'] for r in read_csv(directory / 'nodes.csv')}
            edges = read_csv(directory / 'edges.csv')
            triples = {(r['src'], r['dst'], r['eventID']) for r in edges}
            expected = {tuple(a) for a in case['accesses']}
            matched = expected & triples
            target_hits = set(case['targets']) & nodes
            evidence = [dict(src=r['src'], dst=r['dst'], eventID=r['eventID'],
                             api=r['eventName'], refPath=r['refPath']) for r in edges
                        if (r['src'], r['dst'], r['eventID']) in expected]
            record['levels'][str(level)] = dict(target_hits=len(target_hits), access_hits=len(matched),
                target_recall=len(target_hits)/len(case['targets']), access_recall=len(matched)/len(expected),
                missing_targets=sorted(set(case['targets'])-nodes),
                missing_accesses=sorted(expected-triples), matched_evidence=evidence)
        results.append(record)
    report = dict(parser_sha256=digest(ROOT / 'parser_node3_v2.py'), results=results)
    (OUT / 'summary.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    for r in results:
        print(r['scenario'], 'targets',r['required_targets'], 'accesses',r['required_accesses'],
              {lv:(m['target_hits'],m['access_hits']) for lv,m in r['levels'].items()})


if __name__ == '__main__':
    main()
