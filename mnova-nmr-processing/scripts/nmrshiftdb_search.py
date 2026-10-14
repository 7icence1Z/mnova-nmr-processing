"""Opt-in unknown-structure candidate lookup; Python 3.9+ standard library only."""
import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

BASE = 'https://nmrshiftdb.nmr.uni-koeln.de/NmrshiftdbServlet/nmrshiftdbaction'
MAX_BYTES = 8 * 1024 * 1024


def number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(label + ' must be a finite JSON number')
    return float(value)


def validate_request(data):
    if not isinstance(data, dict) or data.get('mode') != 'guess_structure':
        raise ValueError('Only mode=guess_structure is supported; do not call for routine known-structure validation')
    clues = data.get('clues')
    if not isinstance(clues, dict) or not any(isinstance(v, str) and v.strip() for v in clues.values()):
        raise ValueError('Provide real structural clues before a candidate search')
    formula = clues.get('molecular_formula')
    if formula is not None and (not isinstance(formula, str) or not re.fullmatch(r'(?:[A-Z][a-z]?\d*)+', formula)):
        raise ValueError('molecular_formula must be an exact formula, e.g. C2H6O (no regex or ranges)')
    if data.get('nucleus') not in ('1H', '13C'):
        raise ValueError('nucleus must explicitly be 1H or 13C')
    signals = data.get('signals')
    if not isinstance(signals, list) or not 1 <= len(signals) <= 128:
        raise ValueError('signals must contain 1 to 128 manually reviewed resonance groups')
    shifts = []
    for signal in signals:
        if not isinstance(signal, dict):
            raise ValueError('Each signal must contain delta; use resonance centers, not splitting lines')
        shifts.append(number(signal.get('delta'), 'delta'))
    if len(set(shifts)) != len(shifts):
        raise ValueError('Duplicate resonance centers; review equivalent/overlapping signals before searching')
    if not formula and len(shifts) < 2:
        raise ValueError('A single shift without a formula is too broad for automated search')
    tolerance = number(data.get('tolerance_ppm'), 'tolerance_ppm')
    if tolerance <= 0:
        raise ValueError('tolerance_ppm must be positive and selected for the current data')
    if data.get('search_mode', 'whole') not in ('whole', 'sub'):
        raise ValueError('search_mode must be whole or sub')
    return shifts, formula, tolerance


def build_url(data):
    shifts, formula, _ = validate_request(data)
    if formula:
        # Narrow a clue-supported candidate set, then compare actual stored shifts locally.
        return BASE + '/doSearch/searchfield/chemical%20formula/searchstring/' + urllib.parse.quote(formula, safe='')
    peaks = ''.join(format(shift, '.10g') + '|' for shift in shifts)
    return BASE + '/dereplicate/searchspectrum/' + urllib.parse.quote(peaks, safe='') + '?' + urllib.parse.urlencode({
        'spectrumtype': data['nucleus'], 'subspectrum': data.get('search_mode', 'whole')})


def local_name(tag):
    return tag.rsplit('}', 1)[-1]


def parse_cml(body):
    try:
        root = ET.fromstring(body)
    except ET.ParseError as error:
        raise ValueError('Service returned non-CML data (possibly an HTTP-200 HTML error page)') from error
    if local_name(root.tag) not in ('cml', 'moleculeList'):
        raise ValueError('Service returned an unexpected root element: ' + local_name(root.tag))
    molecules = {}
    for node in root.iter():
        if local_name(node.tag) != 'molecule' or not node.get('id'):
            continue
        identity = node.get('id')
        meta = {el.get('name', ''): el.get('content', '') for el in node.iter() if local_name(el.tag) == 'metadata'}
        digits = re.fullmatch(r'nmrshiftdb(\d+)', identity)
        molecules[identity] = {
            'id': identity, 'name': node.get('title') or meta.get('qname:name'),
            'url': 'https://nmrshiftdb.nmr.uni-koeln.de/molecule/' + digits.group(1) if digits else None,
            'database_similarity': meta.get('qname:similarity'), 'spectra': []}
    for node in root.iter():
        if local_name(node.tag) != 'spectrum':
            continue
        parent = molecules.get(node.get('moleculeRef'))
        if parent is None:
            continue
        meta = {el.get('name', ''): el.get('content', '') for el in node.iter() if local_name(el.tag) == 'metadata'}
        program = meta.get('nmr:Program', '').strip()
        # An ID alone does not make a record experimental. No evidence => unknown.
        evidence = 'calculated' if program and program.lower() not in ('unreported', 'unknown') else 'unknown'
        explicit = meta.get('nmr:measured', '').lower()
        if not program and explicit == 'true':
            evidence = 'measured'
        solvent = next((el.get('title') for el in node.iter() if local_name(el.tag) == 'substance' and el.get('dictRef', '').endswith(':solvent')), None)
        field = next((el.text for el in node.iter() if local_name(el.tag) == 'scalar' and el.get('dictRef', '').endswith(':field')), None)
        shifts = []
        for peak in node.iter():
            if local_name(peak.tag) == 'peak' and peak.get('xValue') is not None:
                if not peak.get('xUnits', '').lower().endswith('ppm'):
                    continue
                value = float(peak.get('xValue'))
                if math.isfinite(value):
                    shifts.append(value)
        parent['spectra'].append({'id': node.get('id'), 'nucleus': meta.get('nmr:OBSERVENUCLEUS'),
                                  'provenance': evidence, 'program': program or None,
                                  'solvent': solvent, 'frequency_mhz': field, 'shifts': sorted(set(shifts))})
    return list(molecules.values())


def match_shifts(query, reference, tolerance, mode):
    """Ordered one-to-one match: maximize matches, then minimize total ppm error."""
    query, reference = sorted(query), sorted(reference)
    rows, cols = len(query), len(reference)
    best = [[(0, 0.0)] * (cols + 1) for _ in range(rows + 1)]
    for i in range(1, rows + 1):
        for j in range(1, cols + 1):
            options = [best[i-1][j], best[i][j-1]]
            error = abs(query[i-1] - reference[j-1])
            if error <= tolerance:
                prev = best[i-1][j-1]
                options.append((prev[0] + 1, prev[1] - error))
            best[i][j] = max(options)
    count, negative_error = best[rows][cols]
    return {'matched_groups': count, 'query_groups': rows, 'reference_groups': cols,
            'query_coverage': count / rows if rows else 0,
            'reference_coverage': count / cols if cols else 0,
            'shift_coverage_score': count / (rows if mode == 'sub' else max(rows, cols)) if max(rows, cols) else 0,
            'matched_mae_ppm': -negative_error / count if count else None}


def summarize(candidates, data, limit):
    query, _, tolerance = validate_request(data)
    excluded = 0
    comparable = 0
    matched = 0

    def comparison_rank(comparison):
        mae = comparison['matched_mae_ppm']
        return comparison['shift_coverage_score'], -mae if mae is not None else -math.inf

    for candidate in candidates:
        usable = []
        for spectrum in candidate['spectra']:
            if spectrum['nucleus'] != data['nucleus']:
                continue
            if spectrum['provenance'] == 'calculated':
                excluded += 1
                continue
            if spectrum['shifts']:
                spectrum['comparison'] = match_shifts(query, spectrum['shifts'], tolerance, data.get('search_mode', 'whole'))
                usable.append(spectrum)
        candidate['spectra'] = usable
        best = max((s['comparison'] for s in usable), key=comparison_rank, default=None)
        candidate['best_shift_score'] = best['shift_coverage_score'] if best else None
        candidate['best_shift_mae_ppm'] = best['matched_mae_ppm'] if best else None
        comparable += best is not None
        matched += best is not None and best['matched_groups'] > 0
        candidate['verification'] = 'candidate_only_not_identified'
    candidates.sort(key=lambda c: (c['best_shift_score'] if c['best_shift_score'] is not None else -1,
                                   -c['best_shift_mae_ppm'] if c['best_shift_mae_ppm'] is not None else -math.inf), reverse=True)
    return {'returned_molecules': len(candidates), 'comparable_molecules': comparable,
            'shift_matched_molecules': matched, 'excluded_calculated_spectra': excluded,
            'candidates': candidates[:limit],
            'limitations': ['Coverage is a shift-only heuristic, not an identity probability; compare integrals, multiplicity, J, clues and solvent manually.',
                            'Unknown provenance is not experimental confirmation. Calculated spectra are excluded; missing measured flags remain unknown.',
                            'Unknown structures retain relative integrals unless an absolute H-count anchor is independently justified.',
                            'No candidate can be declared confirmed from database rank; check E/Z and stereochemistry separately.']}


def search(data, output, timeout=30, limit=5):
    url = build_url(data)  # Authorization mode and clues checked before network or file creation.
    if not math.isfinite(timeout) or timeout <= 0 or not 1 <= limit <= 20:
        raise ValueError('timeout must be finite/positive and limit must be 1..20')
    output = Path(output).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    record = {'status': 'failed', 'mode': 'guess_structure', 'query_url': url,
              'queried_at': datetime.now(timezone.utc).isoformat(),
              'request': data, 'backend': 'formula_then_local_shifts' if data['clues'].get('molecular_formula') else 'dereplicate'}
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'mnova-nmr-processing/1.0', 'Accept': 'chemical/x-cml, application/xml, text/xml'})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            record['http_status'] = response.status
            body = response.read(MAX_BYTES + 1)
        (output / 'response.cml').write_bytes(body)
        if len(body) > MAX_BYTES:
            raise ValueError('Response exceeds 8 MiB; narrow structural clues instead of dumping more records')
        candidates = parse_cml(body)
        record.update(summarize(candidates, data, limit))
        if not record['returned_molecules']:
            record['status'] = 'no_match'
        elif not record['comparable_molecules']:
            record['status'] = 'no_usable_spectra'
        elif not record['shift_matched_molecules']:
            record['status'] = 'no_shift_match'
        else:
            record['status'] = 'candidates_found'
    except (OSError, ValueError, ET.ParseError) as error:
        record['error'] = str(error)
        record['next_step'] = 'Service failure is not no_match. Retain processed spectrum; do not infer an identity or auto-deploy another model.'
    (output / 'result.json').write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', required=True, help='JSON with mode=guess_structure, clues, nucleus, signals and tolerance_ppm')
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--timeout', type=float, default=30)
    parser.add_argument('--limit', type=int, default=5)
    args = parser.parse_args()
    try:
        data = json.loads(Path(args.request).expanduser().read_text(encoding='utf-8-sig'))
        result = search(data, args.output_dir, args.timeout, args.limit)
        # Full response stays on disk; keep model context compact.
        print(json.dumps({'status': result['status'], 'result_file': str(Path(args.output_dir).expanduser().resolve() / 'result.json'),
                          'comparable_molecules': result.get('comparable_molecules'),
                          'shift_matched_molecules': result.get('shift_matched_molecules'),
                          'candidates': [{'id': c['id'], 'name': c['name'], 'shift_score': c['best_shift_score'],
                                          'matched_mae_ppm': c['best_shift_mae_ppm']} for c in result.get('candidates', [])],
                          'error': result.get('error')}, ensure_ascii=False, indent=2))
        return 1 if result['status'] == 'failed' else 0
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
