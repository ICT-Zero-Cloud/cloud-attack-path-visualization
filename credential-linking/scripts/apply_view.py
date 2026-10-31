#!/usr/bin/env python3
"""
apply_view.py — 기반 CSV(3-node v2) → 뷰(G_j2v) CSV 로 물질화한다.

뷰 규칙을 새로 구현하지 않는다. 같은 폴더의 simulate_views.py 함수를 그대로
재사용하므로 enrich_views.cypher 와 동일한 결과가 나온다(진리원본 1개 유지).

입력 : 기반 CSV 디렉터리 (nodes.csv / edges.csv / context.csv)
출력 : 뷰 CSV 디렉터리 (기본 <기반dir>_view)
        nodes.csv    + nodeKind(:Credential/:Identity/:Workload/:Asset), finding, sourceIPs
        edges.csv    + advances(true/false)
        context.csv  (기반 그대로 복사)
        canobtain.csv  합성 엣지: src,dst,rel,exercised,viaWorkloads,at,controlEvents

사용:
    python apply_view.py <기반csv디렉터리> [출력디렉터리]
    예)  python apply_view.py ../csv/aws.5_chain_n1
         → ../csv/aws.5_chain_n1_view/ 생성
"""
import csv
import os
import shutil
import sys
from collections import Counter
from pathlib import Path

# 같은 디렉터리의 simulate_views 를 import (뷰 규칙 재사용)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import simulate_views as sv  # noqa: E402


def main():
    if len(sys.argv) < 2:
        print("usage: python apply_view.py <base_csv_dir> [out_dir]")
        sys.exit(1)
    base = Path(sys.argv[1])
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(str(base).rstrip('/') + '_view')

    N, E, C = sv.load(base)                      # 기반 그래프 로드
    splits, ip_of = sv.split_identity(N, E, C)   # STEP4: 신원 분열
    CAN = sv.can_obtain(E, C)                     # STEP3: CAN_OBTAIN 합성

    split_wl = {w for (w, keys, ips) in splits}
    split_keys = {k for (w, keys, ips) in splits for (k, kips) in keys}

    out.mkdir(parents=True, exist_ok=True)

    # ── nodes.csv (+ nodeKind / finding / sourceIPs) ───────────────────────
    with open(base / 'nodes.csv', encoding='utf-8') as f:
        node_fields = list(csv.DictReader(f).fieldnames)
    new_node_fields = node_fields + ['nodeKind', 'finding', 'sourceIPs']
    with open(out / 'nodes.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=new_node_fields, extrasaction='ignore')
        w.writeheader()
        for nid, n in N.items():
            row = dict(n)
            row['nodeKind'] = sv.node_kind(n)
            row['finding'] = ('split-workload' if nid in split_wl
                              else 'split-identity' if nid in split_keys else '')
            row['sourceIPs'] = '|'.join(sorted(ip_of.get(nid, [])))
            w.writerow(row)

    # ── edges.csv (+ advances) ─────────────────────────────────────────────
    with open(base / 'edges.csv', encoding='utf-8') as f:
        edge_fields = list(csv.DictReader(f).fieldnames)
    new_edge_fields = edge_fields + ['advances']
    with open(out / 'edges.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=new_edge_fields, extrasaction='ignore')
        w.writeheader()
        for e in E:
            row = dict(e)
            row['advances'] = 'true' if sv.advances(e) else 'false'
            w.writerow(row)

    # ── context.csv (그대로 복사) ──────────────────────────────────────────
    shutil.copyfile(base / 'context.csv', out / 'context.csv')

    # ── canobtain.csv (합성 엣지) ──────────────────────────────────────────
    can_fields = ['src', 'dst', 'rel', 'exercised', 'viaWorkloads', 'at', 'controlEvents']
    ex_count = 0
    with open(out / 'canobtain.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=can_fields)
        w.writeheader()
        for (a, b), d in CAN.items():
            exercised = bool(ip_of.get(a, set()) & ip_of.get(b, set()))
            ex_count += 1 if exercised else 0
            w.writerow({'src': a, 'dst': b, 'rel': 'CAN_OBTAIN',
                        'exercised': 'true' if exercised else 'false',
                        'viaWorkloads': '|'.join(sorted(d['via'])),
                        'at': d['at'], 'controlEvents': d['n']})

    adv = Counter(sv.advances(e) for e in E)
    kd = Counter(sv.node_kind(n) for n in N.values())
    print(f"[apply_view] {base}  ->  {out}")
    print(f"  nodes {len(N)} | edges {len(E)} (advances true {adv[True]} / false {adv[False]})"
          f" | context {len(C)}")
    print(f"  CAN_OBTAIN {len(CAN)} (exercised {ex_count}) | nodeKind {dict(kd)}")
    print(f"  finding: split-workload {len(split_wl)} / split-identity {len(split_keys)}")


if __name__ == '__main__':
    main()
