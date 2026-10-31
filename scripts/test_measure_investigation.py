"""Small implementation checks; these are not additional attack scenarios."""
import copy
import json
import unittest
from pathlib import Path
import measure_investigation as m


class InvestigationChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.gt = json.loads((root / 'groundtruth_json/aws.5_chain_n4.investigation.json').read_text(encoding='utf-8'))
        cls.edges = m.load_edges(root / 'csv/aws.5_chain_n4')

    def selected(self, edges=None):
        w = self.gt['window']
        return m.proposed(self.edges if edges is None else edges, self.gt['anchor_event'], w['from'], w['to'])[2]

    def test_wrong_endpoint_is_false_positive(self):
        rows = copy.deepcopy(self.selected())
        required = tuple(self.gt['required_connections'][2])
        row = next(r for r in rows if (m.rel_cat(r), r['src'], r['dst'], r['eventID']) == required)
        row['dst'] = 'ASIA_WRONG_KEY'
        result = m.evaluate(rows, self.gt)
        self.assertEqual(result['connections']['false'], 1)
        self.assertEqual(result['connections']['hits'], 5)
        self.assertFalse(result['complete'])

    def test_reversed_time_is_incomplete(self):
        rows = copy.deepcopy(self.selected())
        secret_id = self.gt['required_connections'][4][3]
        for row in rows:
            if row['eventID'] == secret_id:
                row['eventTime'] = '2026-09-10T06:13:20Z'
        self.assertFalse(m.evaluate(rows, self.gt)['complete'])

    def test_use_before_issuance_is_excluded(self):
        rows = copy.deepcopy(self.edges)
        early = copy.deepcopy(next(r for r in rows if r['eventID'] == self.gt['required_connections'][4][3]))
        early.update(eventID='test-before-issuance', eventTime='2026-09-10T06:13:20Z')
        rows.append(early)
        self.assertNotIn(early['eventID'], {r['eventID'] for r in self.selected(rows)})

    def test_wrong_role_is_incomplete(self):
        rows = copy.deepcopy(self.selected())
        role = tuple(self.gt['same_role_checks'][0][1])
        for row in rows:
            if (m.rel_cat(row), row['src'], row['dst'], row['eventID']) == role:
                row['dst'] += '-other'
        result = m.evaluate(rows, self.gt)
        self.assertFalse(result['checks']['same_role_1'])
        self.assertEqual(result['connections']['false'], 1)

    def test_duplicate_rows_do_not_inflate_counts(self):
        rows = self.selected()
        self.assertEqual(m.evaluate(rows, self.gt), m.evaluate(rows + rows, self.gt))

    def test_handoff_modes_and_witnesses(self):
        control=dict(src='AKIA_A',dst='workload',rel='ACCESS',eventID='control',
                     eventName='SendCommand',eventTime='2026-09-10T06:13:20Z',
                     outcome='SUCCESS',dstAs='Resource',sourceIP='1.2.3.4')
        use=dict(control,src='ASIA_B',dst='secret',eventID='use',eventName='GetSecretValue',
                 eventTime='2026-09-10T06:13:30Z')
        context=[dict(src='ASIA_B',dst='workload',rel='RUNS_ON')]
        candidates=[dict(src='AKIA_A',dst='ASIA_B',viaWorkloads='workload')]
        f,to='2026-09-10T06:13:00Z','2026-09-10T06:14:00Z'
        h=m.candidate_handoffs([control,use],context,candidates,f,to)
        self.assertEqual(len(h),1)
        self.assertEqual(m.proposed([control,use],'control',f,to)[0],{'control'})
        chosen=[]
        self.assertEqual(m.proposed([control,use],'control',f,to,h,True,chosen)[0],{'control','use'})
        self.assertEqual(len(chosen),1)
        self.assertNotIn('',m.proposed([control,use],'control',f,to,h,True)[0])
        self.assertFalse(m.candidate_handoffs([control,dict(use,eventTime=f)],context,candidates,f,to))
        self.assertFalse(m.candidate_handoffs([control,dict(use,sourceIP='9.9.9.9')],context,candidates,f,to))
        self.assertTrue(m.candidate_handoffs([control,dict(use,sourceIP='9.9.9.9')],context,candidates,f,to,False))


if __name__ == '__main__':
    unittest.main()
