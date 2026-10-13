"""Offline regressions: policy boundaries, data integrity, and replay totals."""
import csv
import importlib.util
import statistics
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'core'))
import policy_engine as p
import app

class PolicyTests(unittest.TestCase):
    def test_rtt_edges(self):
        for rtt, expected in [(0,p.GROUP_1024),(49.999,p.GROUP_1024),(50,p.GROUP_768),(100,p.GROUP_768),(100.001,p.GROUP_512)]:
            with self.subTest(rtt=rtt): self.assertEqual(p.network_candidate(rtt),expected)

    def test_stricter_resource_wins_and_boundaries(self):
        for cpu, mem, tier in [(60,256,'High-performance'),(15,64,'Mid-range'),(14.9,1024,'Constrained'),(100,63.9,'Constrained'),(59.9,1024,'Mid-range'),(100,255.9,'Mid-range')]:
            with self.subTest(cpu=cpu,mem=mem): self.assertEqual(p.classify_device(cpu,mem),tier)

    def test_nine_conditions(self):
        for cpu,mem,expected in [(None,None,[p.GROUP_1024,p.GROUP_768,p.GROUP_512]),(25,128,[p.GROUP_768,p.GROUP_768,p.GROUP_512]),(10,32,[p.GROUP_512]*3)]:
            actual=[p.select_group(dict(rtt_ms=rtt,cpu_share_pct=cpu,mem_limit_mb=mem)).group for rtt in [20,70,120]]
            self.assertEqual(actual,expected)

class DatasetTests(unittest.TestCase):
    def test_frozen_integrity(self):
        spec=importlib.util.spec_from_file_location('integrity', ROOT/'analysis/verify_integrity.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        count,failures=module.verify();self.assertEqual(count,11);self.assertEqual(failures,[])

    def test_data_shape_and_unique_trials(self):
        self.assertEqual(len(app.DATASET.rows),1800)
        self.assertEqual(len(app.DATASET.crypto_rows),450)
        keys=[tuple(r[k] for k in ['enforced_profile','network_profile','config','trial']) for r in app.DATASET.rows]
        self.assertEqual(len(set(keys)),1800)
        for dev in app.DEVICE_PROFILES:
            for net in app.NETWORK_PROFILES:
                for row in app.DATASET.compare(dev,net): self.assertEqual(row['trials'],50)

    def test_replay_matches_original_policy(self):
        for dev in app.DEVICE_PROFILES:
            for net in app.NETWORK_PROFILES:
                session=app.replay_session(dev,net)
                self.assertEqual(session['selected_group'],session['policy']['final_group'])
                self.assertEqual(session['mode'],'replay')

    def test_total_is_median_of_paired_sums(self):
        cell=app.DATASET._cell('Constrained','Moderate','Adaptive')
        expected=statistics.median(float(r['wire_latency_ms'])+float(r['probe_cost_ms']) for r in cell)
        actual=app.DATASET.summary('Constrained','Moderate','Adaptive')['first_connection_cost_ms']
        self.assertAlmostEqual(actual,expected,places=4)
        self.assertAlmostEqual(actual,221.785,places=3)

    def test_invalid_api_numbers_rejected(self):
        for value in [-1,float('nan'),float('inf'),5001,'abc']:
            with self.subTest(value=value),self.assertRaises(ValueError):
                app.parse_nullable_number(value,minimum=0,maximum=5000,label='RTT')

if __name__=='__main__': unittest.main()
