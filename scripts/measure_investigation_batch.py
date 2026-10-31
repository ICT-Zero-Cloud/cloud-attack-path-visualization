"""Run the frozen n1-n4 investigation GTs with the same two query modes."""
import json
import subprocess
import sys
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    results = []
    for i in range(1, 5):
        output = root / f'results/common_investigation_n{i}.json'
        subprocess.run([sys.executable, '-X', 'utf8',
                        str(root / 'scripts/measure_investigation.py'),
                        '--gt', str(root / f'groundtruth_json/aws.5_chain_n{i}.common.json'),
                        '--csv', str(root / f'csv/aws.5_chain_n{i}_view'),
                        '--mode', 'both', '--output', str(output)], check=True,
                       stdout=subprocess.PIPE, encoding='utf-8')
        result = json.loads(output.read_text(encoding='utf-8'))
        selected = result['strategies']['proposed_inferred']
        baseline = result['strategies']['time_window']
        observed = result['strategies']['proposed']
        results.append(dict(scenario=f'n{i}', window=result['window'],
                            required_events=selected['events']['required'],
                            event_hits=selected['events']['hits'],
                            required_connections=selected['connections']['required'],
                            connection_hits=selected['connections']['hits'],
                            window_events=baseline['returned_events'],
                            proposed_events=selected['returned_events'],
                            complete=selected['complete'],
                            reduction=selected['reduction_vs_window'],
                            observed_events=observed['returned_events'],
                            observed_event_hits=observed['events']['hits'],
                            observed_connection_hits=observed['connections']['hits'],
                            candidate_pairs=result['inferred_handoff_pairs']))
    (root / 'results/common_investigation_summary.json').write_text(
        json.dumps(results, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    for r in results:
        print(r)


if __name__ == '__main__':
    main()
