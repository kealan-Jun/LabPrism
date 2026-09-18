#!/usr/bin/env python3
"""Verify every analyzed RGB frame against decoded video; optionally compare a rerun."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from labprism.artifacts import sha256, verify_run


def inspect(run):
    import av
    result = verify_run(run)
    expected = {f['frame_index']: f for f in result['frames']}
    checked = 0
    with av.open(str(run/'clip.mp4')) as video:
        for index, frame in enumerate(video.decode(video=0)):
            if index not in expected:
                continue
            record = expected[index]
            if abs(float(frame.pts*frame.time_base)*1000-record['timestamp_ms']) > .001:
                raise ValueError(f'{run.name}: decoded PTS mismatch at {index}')
            if hashlib.sha256(frame.to_ndarray(format='rgb24').tobytes()).hexdigest() != record['rgb_sha256']:
                raise ValueError(f'{run.name}: RGB identity mismatch at {index}')
            checked += 1
    if checked != len(expected):
        raise ValueError('Recorded frame missing from video')
    return result, checked


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('catalog', type=Path)
    p.add_argument('--compare-root', type=Path)
    p.add_argument('--output', required=True, type=Path)
    args = p.parse_args()
    report = {'schema_version':'labprism-replay-verification/1', 'created_at':datetime.now(timezone.utc).isoformat(),
              'quality_acceptance':False, 'independent_ground_truth':False, 'clips':[]}
    for entry in json.loads(args.catalog.read_text())['clips']:
        run = Path(entry['run'])
        result, checked = inspect(run)
        item = {'id':entry['id'], 'run':str(run), 'receipt_sha256':sha256(run/'receipt.json'),
                'decoded_rgb_frames_verified':checked, 'metrics':result['metrics'], 'reproduction':None}
        if args.compare_root:
            other_run = args.compare_root/entry['id']
            other, count = inspect(other_run)
            if result['source'] != other['source'] or result['models'] != other['models'] or result['configuration'] != other['configuration']:
                raise ValueError('Comparison inputs/configurations differ')
            fields = ['frame_index','timestamp_ms','rgb_sha256','objects','hands','availability']
            matched = sum(all(a[k] == b[k] for k in fields) for a,b in zip(result['frames'], other['frames']))
            item['reproduction'] = {'run':str(other_run), 'receipt_sha256':sha256(other_run/'receipt.json'),
                                    'frames':count, 'identical_prediction_frames':matched,
                                    'all_predictions_identical':count == checked == matched, 'metrics':other['metrics']}
        report['clips'].append(item)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as output:
        output.write(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({'report':str(args.output), 'clips':len(report['clips']),
                      'frames_verified':sum(c['decoded_rgb_frames_verified'] for c in report['clips'])}))


if __name__ == '__main__':
    main()
