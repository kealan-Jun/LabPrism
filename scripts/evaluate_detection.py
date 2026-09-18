#!/usr/bin/env python3
"""Evaluate baseline and context filter on an AW-owned frozen validation export."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from labprism.artifacts import sha256
from labprism.evaluation import counts, load_validation, summarize
from labprism.perception.baseline import source_revision
from labprism.tracking.association import reject_screen_conflicts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('export', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--models', type=Path, required=True)
    parser.add_argument('--candidate', choices=['screen_filter', 'higher_resolution'], default='screen_filter')
    args = parser.parse_args()
    receipt, selected = load_validation(args.export)
    registry = json.loads(args.models.read_text())
    needed = [m for m in registry['models'] if m['task'] in {'object_detection', 'object_context_verification'}]
    for model in needed:
        if sha256(model['path']) != model['sha256']:
            raise ValueError('Model hash mismatch')
    from ultralytics import YOLO
    import torch
    if not torch.cuda.is_available():
        raise RuntimeError('GPU evaluation required')
    detectors = {m['role']: YOLO(m['path']) for m in needed if m['task'] == 'object_detection'}
    context = YOLO(next(m['path'] for m in needed if m['task'] == 'object_context_verification'))
    args.output.mkdir(parents=True, exist_ok=False)
    rows = []
    for item in selected:
        role = item['record']['role']
        def infer(model, imgsz=960):
            result = model(str(item['path']), device=0, imgsz=imgsz, conf=.25, verbose=False)[0]
            return [{'label': result.names[int(b.cls.item())], 'confidence': float(b.conf.item()),
                     'box': [float(v) for v in b.xyxy[0].tolist()]} for b in result.boxes]
        torch.cuda.synchronize(); started=time.perf_counter()
        baseline = infer(detectors[role])
        torch.cuda.synchronize(); baseline_ms=(time.perf_counter()-started)*1000
        started=time.perf_counter(); contexts=[]; rejected=[]
        if args.candidate == 'screen_filter':
            contexts = infer(context)
            candidate, rejected = reject_screen_conflicts(baseline, contexts)
        else:
            candidate = infer(detectors[role], imgsz=1280)
        torch.cuda.synchronize(); candidate_ms=(time.perf_counter()-started)*1000
        row = {'image_id': item['record']['image_id'], 'revision': item['record']['revision'], 'role': role,
               'source_sha256': item['record']['source_sha256'], 'baseline_exposure': item['row']['source'].get('baseline_exposure', 'unknown'),
               'source_group': item['row']['source'].get('source_group'),
               'baseline_predictions': baseline, 'candidate_predictions': candidate,
               'context_predictions': contexts, 'rejected': rejected,
               'baseline_call_ms': baseline_ms, 'candidate_call_ms': candidate_ms}
        for name, predictions in [('baseline', baseline), ('candidate', candidate)]:
            row[name+'_counts'], row[name+'_matches'] = counts(predictions, item['truth'])
        rows.append(row)
    report = {'schema_version': 'labprism-detection-regression/1', 'created_at': datetime.now(timezone.utc).isoformat(),
              'producer_receipt': str(args.export/'receipt.json'), 'producer_receipt_sha256': sha256(args.export/'receipt.json'),
              'annotation_snapshot_sha256': receipt['files']['annotations.json'], 'models': needed,
              'config': {'candidate': args.candidate, 'confidence': .25, 'baseline_imgsz': 960, 'candidate_imgsz': 1280 if args.candidate=='higher_resolution' else 960, 'match_iou': .5, 'matching': 'confidence_ordered_class_aware_one_to_one'},
              'truth_status': receipt['truth_status'], 'independent_ground_truth': False,
              'scope': 'exposed_internal_project_regression_not_generalization', 'promotion': False,
              'limitations': ['16 first-person validation images exposed to baseline; two third-person images are crops with unknown exposure',
                             'Camera roles follow project review; original camera installation not verified',
                             'Fixed-threshold precision/recall, not AP; no final test data accessed',
                             'No keypoint/mask/track ground truth; no new training or dataset ownership transfer'],
              'roles': {}, 'images': rows, **source_revision(Path(__file__).resolve().parents[1])}
    for role in detectors:
        records = [r for r in rows if r['role'] == role]
        report['roles'][role] = {'images': len(records), 'rejected': sum(len(r['rejected']) for r in records),
                                 **{name: summarize([r[name+'_counts'] for r in records]) for name in ['baseline', 'candidate']}}
    (args.output/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(report['roles'], ensure_ascii=False))


if __name__ == '__main__':
    main()
