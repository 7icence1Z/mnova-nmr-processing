import importlib.util
import contextlib
import io
import json
from pathlib import Path
import tempfile
import sys
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('search', Path(__file__).parents[1] / 'mnova-nmr-processing/scripts/nmrshiftdb_search.py')
search = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(search)

REQUEST = {'mode': 'guess_structure', 'clues': {'molecular_formula': 'C2H6O'}, 'nucleus': '1H',
           'signals': [{'delta': 1.17, 'relative_integral': 3}, {'delta': 3.64, 'relative_integral': 2}],
           'tolerance_ppm': 0.1}
CML = b'''<moleculeList xmlns="http://www.xml-cml.org/schema"><cml>
<molecule id="nmrshiftdb123" title="test candidate"/>
<spectrum moleculeRef="nmrshiftdb123" id="exp1"><metadataList>
<metadata name="nmr:OBSERVENUCLEUS" content="1H"/>
</metadataList><peakList><peak xValue="1.18" xUnits="units:ppm"/><peak xValue="3.65" xUnits="units:ppm"/></peakList></spectrum>
<spectrum moleculeRef="nmrshiftdb123" id="calculated-record-with-id"><metadataList>
<metadata name="nmr:OBSERVENUCLEUS" content="1H"/><metadata name="nmr:Program" content="HOSE code predictor"/>
</metadataList><peakList><peak xValue="1.17" xUnits="units:ppm"/></peakList></spectrum>
</cml></moleculeList>'''


class Response:
    status = 200
    def __init__(self, body):
        self.body = body
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self, limit):
        return self.body[:limit]


class SearchTests(unittest.TestCase):
    def test_known_structure_mode_never_calls_network(self):
        data = dict(REQUEST, mode='known_structure')
        with tempfile.TemporaryDirectory() as tmp, patch.object(search.urllib.request, 'urlopen') as network:
            with self.assertRaises(ValueError):
                search.search(data, Path(tmp) / 'not-created')
            network.assert_not_called()
            self.assertFalse((Path(tmp) / 'not-created').exists())

    def test_missing_clues_and_invalid_shifts_fail_before_network(self):
        for data in (dict(REQUEST, clues={}), dict(REQUEST, signals=[{'delta': float('nan')}]),
                     dict(REQUEST, clues={'molecular_formula': 'C.*'}), dict(REQUEST, tolerance_ppm=0)):
            with self.subTest(data=data), patch.object(search.urllib.request, 'urlopen') as network:
                with self.assertRaises(ValueError):
                    search.build_url(data)
                network.assert_not_called()

    def test_http200_html_is_failure_not_no_match(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(search.urllib.request, 'urlopen', return_value=Response(b'<img src="bug.png">An error occurred')):
            result = search.search(REQUEST, tmp)
            self.assertEqual(result['status'], 'failed')
            self.assertIn('non-CML', result['error'])
            self.assertTrue((Path(tmp) / 'response.cml').exists())

    def test_empty_cml_is_no_match(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(search.urllib.request, 'urlopen', return_value=Response(b'<cml xmlns="http://www.xml-cml.org/schema"/>')):
            self.assertEqual(search.search(REQUEST, tmp)['status'], 'no_match')

    def test_calculated_record_id_does_not_make_it_measured(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(search.urllib.request, 'urlopen', return_value=Response(CML)):
            result = search.search(REQUEST, tmp)
            self.assertEqual(result['status'], 'candidates_found')
            self.assertEqual(result['excluded_calculated_spectra'], 1)
            candidate = result['candidates'][0]
            self.assertEqual(candidate['verification'], 'candidate_only_not_identified')
            self.assertEqual(candidate['spectra'][0]['provenance'], 'unknown')
            self.assertEqual(candidate['spectra'][0]['comparison']['matched_groups'], 2)
            self.assertEqual(json.loads((Path(tmp) / 'result.json').read_text(encoding='utf-8'))['mode'], 'guess_structure')

    def test_reference_resonance_cannot_match_two_query_groups(self):
        result = search.match_shifts([1.1, 1.2], [1.15], 0.1, 'whole')
        self.assertEqual(result['matched_groups'], 1)
        self.assertEqual(result['shift_coverage_score'], 0.5)

    def test_matching_prefers_more_pairs_over_nearest_single_pair(self):
        result = search.match_shifts([1.0, 1.15], [1.1, 1.25], 0.11, 'whole')
        self.assertEqual(result['matched_groups'], 2)

    def test_endpoint_uses_1h_not_api_default_carbon(self):
        data = dict(REQUEST, clues={'reaction_context': 'product has an ethyl fragment'})
        url = search.build_url(data)
        self.assertIn('spectrumtype=1H', url)
        self.assertIn('%7C', url)
        self.assertNotIn('relative_integral', url)

    def test_exact_match_survives_limit_when_coverage_ties(self):
        candidates = [{'id': str(i), 'spectra': [{'nucleus': '1H', 'provenance': 'unknown',
                       'shifts': [1.26, 3.73]}]} for i in range(5)]
        candidates.append({'id': 'exact', 'spectra': [{'nucleus': '1H', 'provenance': 'unknown',
                           'shifts': [1.17, 3.64]}]})
        result = search.summarize(candidates, REQUEST, 5)
        self.assertEqual(result['candidates'][0]['id'], 'exact')
        self.assertEqual(result['candidates'][0]['best_shift_mae_ppm'], 0)
        self.assertEqual(len(result['candidates']), 5)

    def test_best_error_belongs_to_the_best_coverage_spectrum(self):
        candidates = [{'id': 'partial_exact', 'spectra': [
            {'nucleus': '1H', 'provenance': 'unknown', 'shifts': [1.26, 3.73]},
            {'nucleus': '1H', 'provenance': 'unknown', 'shifts': [1.17]}]}]
        result = search.summarize(candidates, REQUEST, 5)['candidates'][0]
        self.assertEqual(result['best_shift_score'], 1)
        self.assertAlmostEqual(result['best_shift_mae_ppm'], 0.09)

    def test_molecule_without_usable_spectra_is_not_a_shift_candidate(self):
        for body in (
            CML.replace(b'content="1H"', b'content="13C"'),
            CML.replace(b'id="exp1"><metadataList>', b'id="exp1"><metadataList><metadata name="nmr:Program" content="predictor"/>'),
            b'<cml><molecule id="formula-only"/></cml>',
        ):
            with self.subTest(body=body), tempfile.TemporaryDirectory() as tmp, patch.object(
                    search.urllib.request, 'urlopen', return_value=Response(body)):
                result = search.search(REQUEST, tmp)
                self.assertEqual(result['status'], 'no_usable_spectra')
                self.assertEqual(result['comparable_molecules'], 0)
                self.assertEqual(result['shift_matched_molecules'], 0)
                self.assertIsNone(result['candidates'][0]['best_shift_score'])

    def test_usable_spectrum_with_no_matching_shifts_has_distinct_status(self):
        body = CML.replace(b'xValue="1.18"', b'xValue="6.18"').replace(b'xValue="3.65"', b'xValue="8.65"')
        with tempfile.TemporaryDirectory() as tmp, patch.object(search.urllib.request, 'urlopen', return_value=Response(body)):
            result = search.search(REQUEST, tmp)
            self.assertEqual(result['status'], 'no_shift_match')
            self.assertEqual(result['comparable_molecules'], 1)
            self.assertEqual(result['shift_matched_molecules'], 0)

    def test_cli_handles_unicode_spaces_and_bom_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / 'Mac 用户 样品'
            folder.mkdir()
            request = folder / 'query 输入.json'
            output = folder / 'search 结果'
            request.write_text(json.dumps(REQUEST, ensure_ascii=False), encoding='utf-8-sig')
            stdout = io.StringIO()
            with patch.object(sys, 'argv', ['nmrshiftdb_search.py', '--request', str(request), '--output-dir', str(output)]), patch.object(
                    search.urllib.request, 'urlopen', return_value=Response(CML)), contextlib.redirect_stdout(stdout):
                code = search.main()
            self.assertEqual(code, 0)
            summary = json.loads(stdout.getvalue())
            self.assertEqual(summary['status'], 'candidates_found')
            self.assertEqual(summary['comparable_molecules'], 1)
            self.assertAlmostEqual(summary['candidates'][0]['matched_mae_ppm'], 0.01)
            self.assertEqual(Path(summary['result_file']), output / 'result.json')
            self.assertEqual((output / 'response.cml').read_bytes(), CML)


if __name__ == '__main__':
    unittest.main()
