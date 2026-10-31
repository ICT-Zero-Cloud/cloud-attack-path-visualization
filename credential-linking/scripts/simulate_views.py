#!/usr/bin/env python3
"""
simulate_views.py (v2) — enrich_views.cypher 를 Neo4j 없이 CSV 위에서 재현한다.

Cypher 와 규칙이 1:1 대응하도록 썼다. 두 결과가 다르면 둘 중 하나가 틀린 것이다.
  STEP 2  advances 마커     (기존 BASE_EVENT 에 표시만, 새 엣지 없음)
  STEP 3  CAN_OBTAIN 합성  (기반에 없는 유일한 새 관계)
  STEP 4  SplitWorkload / SplitIdentity 표시

사용
  python simulate_views.py <csv 디렉터리>
  python simulate_views.py <csv 디렉터리> --seed <노드id> --cutoff 2026-08-21T07:24:01Z
"""
import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path

def load(d: Path):
    def rd(f):
        return list(csv.DictReader(open(d / f, encoding='utf-8')))
    return {n['id']: n for n in rd('nodes.csv')}, rd('edges.csv'), rd('context.csv')


def node_kind(n):
    """STEP 1 — 종류 라벨. 노드당 정확히 하나.

    기준은 'AWS 가 뭐라 부르는가' 가 아니라 '이 그래프에서 무슨 역할을 하는가' 다.
      Credential  행위의 출발점
      Identity    권한을 정의하는 IAM 객체 (Actor 이자 Resource 인 유일한 부류)
      Workload    자격증명이 실리는 곳 (CAN_OBTAIN 의 경유지)
      Asset       나머지 대상 전부
    """
    if n['resourceType'] in ('role', 'instance-profile', 'iam-user', 'iam-policy'):
        return 'Identity'
    if n['kind'] in ('LongTermKey', 'TempKey', 'Service', 'Anonymous'):
        return 'Credential'
    if n['resourceType'] in ('instance', 'launch-template'):
        return 'Workload'
    return 'Asset'


def advances(r):
    """STEP 2 — 도달 전이 마커(불리언). 새 엣지를 만들지 않는다.

    true  = 성공 ∧ 대상특정됨 ∧ (자격증명 획득 OR 상태변경) → 영향/권한이 전이된다
    false = 읽기(노출)·실패·대상미특정. 공격 경로 순회의 잎.
    (5버킷 분류는 없앴다. 노출/정찰/미특정 내역은 base 속성 readOnly/errorClass/dstAs 로.)
    """
    return (r['outcome'] == 'SUCCESS' and r['dstAs'] != 'Service'
            and (r['rel'] == 'OBTAINS' or r['readOnly'] == 'false'))


def can_obtain(E, C):
    """STEP 3 — 기반에 없는 유일한 새 관계.

    (주체가 워크로드를 CONTROL) × (자격증명이 그 워크로드에 RUNS_ON)
      ⇒ (주체)-[:CAN_OBTAIN]->(자격증명)

    방향을 뒤집어 복제하는 게 아니라 두 홉을 접어 '기반에 없던 쌍'을 잇는다.
    """
    runs = defaultdict(set)     # workload -> {cred}
    on = defaultdict(set)       # cred -> {workload}
    for c in C:
        if c['rel'] == 'RUNS_ON':
            runs[c['dst']].add(c['src'])
            on[c['src']].add(c['dst'])
    out = {}
    for r in E:
        if not advances(r):
            continue
        for cred in runs.get(r['dst'], ()):
            if cred == r['src']:
                continue
            # 같은 워크로드에 실린 키끼리는 제외한다. 인스턴스에 실린 키는 그
            # 인스턴스에 CONTROL 을 남기게 마련이라(SSM 에이전트 등), 그대로 두면
            # 같은 인스턴스의 키들이 서로를 CAN_OBTAIN 하는 쌍방향 엣지가 생긴다.
            # 같은 워크로드 안은 이미 같은 신뢰 경계라 '획득'이라 부를 게 없다.
            if r['dst'] in on.get(r['src'], ()):
                continue
            k = (r['src'], cred)
            cur = out.setdefault(k, {'via': set(), 'at': r['eventTime'], 'n': 0})
            cur['via'].add(r['dst'])
            cur['at'] = min(cur['at'], r['eventTime'])
            cur['n'] += 1
    return out


def build_adj(E, CAN):
    """순회 대상: advances 인 BASE_EVENT + CAN_OBTAIN. 전부 정방향."""
    fwd = defaultdict(set)
    for r in E:
        if advances(r) and r['src'] != r['dst']:
            fwd[r['src']].add((r['dst'], 'control', r['eventTime']))
    for (a, b), v in CAN.items():
        fwd[a].add((b, 'can_obtain', v['at']))
    return fwd


def reach(seed, fwd, maxhop=4, cutoff=None, reverse_adj=None):
    adj = reverse_adj if reverse_adj is not None else fwd
    seen = {seed: 0}
    frontier = {seed}
    for h in range(1, maxhop + 1):
        nxt = set()
        for x in frontier:
            for dst, via, t in adj.get(x, ()):
                if cutoff and t > cutoff:
                    continue
                if dst not in seen:
                    seen[dst] = h
                    nxt.add(dst)
        if not nxt:
            break
        frontier = nxt
    return seen


def reverse(fwd):
    rev = defaultdict(set)
    for s, outs in fwd.items():
        for d, via, t in outs:
            rev[d].add((s, via, t))
    return rev


def split_identity(N, E, C):
    """STEP 4 — 같은 워크로드에 실린 키들의 출처 IP 가 갈리는가."""
    ip_of = defaultdict(set)
    for r in E:
        ip = r['sourceIP']
        # sourceIP 는 항상 IP 가 아니다. 서비스 대리 호출이면 도메인이 들어온다.
        if ip and not ip.endswith('.amazonaws.com'):
            ip_of[r['src']].add(ip)
    by_wl = defaultdict(set)
    for c in C:
        if c['rel'] == 'RUNS_ON' and ip_of.get(c['src']):
            by_wl[c['dst']].add(c['src'])
    out = []
    for w, keys in by_wl.items():
        ips = {i for k in keys for i in ip_of[k]}
        if len(ips) >= 2:
            out.append((w, sorted((k, sorted(ip_of[k])) for k in keys), sorted(ips)))
    return out, ip_of


def short(x, n=46):
    return x if len(x) <= n else x[:n - 1] + '…'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('csvdir', type=Path)
    ap.add_argument('--seed', default=None)
    ap.add_argument('--cutoff', default=None)
    args = ap.parse_args()

    N, E, C = load(args.csvdir)
    CAN = can_obtain(E, C)
    fwd = build_adj(E, CAN)

    print(f"\n{'='*76}\n  {args.csvdir}\n{'='*76}")
    print(f"  기반   노드 {len(N)} / BASE_EVENT {len(E)} / CONTEXT {len(C)}")
    print(f"\n  [STEP 1] 노드 종류 라벨")
    for k, v in Counter(node_kind(n) for n in N.values()).most_common():
        print(f"      {k:18} {v}")
    print(f"\n  [STEP 2] advances 마커 (기존 엣지에 표시만)")
    for k, v in Counter(advances(r) for r in E).most_common():
        print(f"      {str(k):18} {v}")
    base_pairs = {(r['src'], r['dst']) for r in E}
    dup = [p for p in CAN if p in base_pairs]
    ipof = defaultdict(set)
    for r in E:
        if r['sourceIP'] and not r['sourceIP'].endswith('.amazonaws.com'):
            ipof[r['src']].add(r['sourceIP'])
    ex = [(a, b) for (a, b) in CAN if ipof.get(a, set()) & ipof.get(b, set())]
    print(f"\n  [STEP 3] CAN_OBTAIN {len(CAN)}개")
    print(f"      기반 BASE_EVENT 가 이미 있는 쌍 : {len(dup)}  ← 0 이어야 복제가 아니다")
    print(f"  [STEP 3b] 그중 exercised (주체 IP 와 대상 키 IP 가 겹침) : {len(ex)}")
    for a, b in sorted(ex):
        print(f"      ★ {a} -> {b}  공유 IP={sorted(ipof[a] & ipof[b])}")

    # ── 뷰 1 ────────────────────────────────────────────────────────
    print(f"\n  [뷰 1] 영향 범위 — 시드별 도달 노드")
    seeds = [args.seed] if args.seed else [n for n in N if node_kind(N[n]) == 'Credential']
    rows = sorted(((len(reach(s, fwd)) - 1, s) for s in seeds), reverse=True)
    for cnt, s in rows[:8]:
        if cnt:
            print(f"      도달 {cnt:3}   {short(s,44):44} ({N[s]['kind']})")
    if rows and rows[0][0]:
        top = rows[0][1]
        seen = reach(top, fwd)
        inside = set(seen)
        ec = len({(r['src'], r['dst']) for r in E
                  if advances(r) and r['src'] in inside and r['dst'] in inside})
        cc = len([p for p in CAN if p[0] in inside and p[1] in inside])
        print(f"\n      {short(top,44)} 유도 부분그래프")
        print(f"        노드 {len(inside)}  전이 대표엣지 {ec}  CAN_OBTAIN {cc}")
        hop = defaultdict(list)
        for nid, h in seen.items():
            hop[h].append(nid)
        for h in sorted(hop):
            kinds = Counter(node_kind(N[x]) for x in hop[h])
            print(f"        h{h}  {len(hop[h]):3}개  {dict(kinds)}")

    # ── 뷰 2 ────────────────────────────────────────────────────────
    if args.seed:
        rev = reverse(fwd)
        print(f"\n  [뷰 2] 유입 경로 — 시드 {short(args.seed,40)}")
        for cut in [None, args.cutoff]:
            if cut is None and args.cutoff is None:
                continue
            seen = reach(args.seed, fwd, cutoff=cut, reverse_adj=rev)
            print(f"      상한 {str(cut or '없음'):24} 상류 {len(seen)-1}개")
            for nid, h in sorted(seen.items(), key=lambda kv: kv[1]):
                if h:
                    print(f"        h{h} {short(nid,52)}")

    # ── 뷰 3 ────────────────────────────────────────────────────────
    splits, ip_of = split_identity(N, E, C)
    print(f"\n  [뷰 3] 세션 신원 분열 — {len(splits)}건")
    for w, keys, ips in splits:
        print(f"      ★ {short(w,60)}")
        print(f"         IPs={ips}")
        for k, kips in keys:
            print(f"         └ {k}  {kips}")
    print()


if __name__ == '__main__':
    main()
