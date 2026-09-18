"""Fixed-threshold detection regression against a frozen producer export."""
import json
import hashlib
from pathlib import Path

from labprism.artifacts import sha256
from labprism.tracking.association import overlap


def match_detections(predictions, truth, iou=.5):
    """Confidence-ordered, class-aware, one-to-one matching; this is not AP."""
    used = set()
    matches = []
    for index in sorted(range(len(predictions)), key=lambda i: -predictions[i]['confidence']):
        pred = predictions[index]
        candidates = [(overlap(pred['box'], gt['box']), j) for j, gt in enumerate(truth)
                      if j not in used and gt['label'] == pred['label']]
        score, target = max(candidates, default=(0, -1))
        if score >= iou and target >= 0:
            used.add(target)
            matches.append({'prediction': index, 'truth': target, 'iou': score})
    return matches


def counts(predictions, truth):
    matches = match_detections(predictions, truth)
    per_class = {}
    for label in sorted({o['label'] for o in predictions + truth}):
        tp = sum(predictions[m['prediction']]['label'] == label for m in matches)
        per_class[label] = {'tp': tp,
                            'fp': sum(p['label'] == label for p in predictions)-tp,
                            'fn': sum(g['label'] == label for g in truth)-tp}
    return per_class, matches


def summarize(rows):
    result = {}
    for row in rows:
        for label, values in row.items():
            total = result.setdefault(label, {'tp': 0, 'fp': 0, 'fn': 0})
            for key in total:
                total[key] += values[key]
    total = {key: sum(v[key] for v in result.values()) for key in ['tp', 'fp', 'fn']}
    for values in [*result.values(), total]:
        tp, fp, fn = (values[k] for k in ['tp', 'fp', 'fn'])
        values['precision'] = tp/(tp+fp) if tp+fp else None
        values['recall'] = tp/(tp+fn) if tp+fn else None
    return {'micro': total, 'per_class': result}


def load_validation(export):
    """Read only val; reject incomplete labels, mutated media, and revision drift."""
    export = Path(export)
    receipt = json.loads((export/'receipt.json').read_text())
    if receipt['schema_version'] != 'annotation-workbench-yolo-export/1':
        raise ValueError('Unsupported producer export')
    if not receipt.get('check',{}).get('export_ready') or not receipt['check'].get('integrity_valid'):
        raise ValueError('Producer export did not pass integrity and quality gates')
    files = receipt['files']
    if sha256(export/'annotations.json') != files['annotations.json']:
        raise ValueError('Annotation snapshot hash mismatch')
    snapshot = json.loads((export/'annotations.json').read_text())
    images = {r['id']: r for r in snapshot['images']}
    if len(images)!=len(snapshot['images']) or len({r['image_id'] for r in receipt['records']})!=len(receipt['records']):
        raise ValueError('Duplicate export records')
    selected = []
    for record in receipt['records']:
        if record['split'] != 'val':
            continue
        role, image_id = record['role'], record['image_id']
        if role not in {'first_person', 'third_person'} or Path(image_id).name != image_id:
            raise ValueError('Invalid role or image identity')
        row = images[image_id]
        annotation = row['annotation']
        annotation_hash=hashlib.sha256(json.dumps(annotation,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
        if annotation_hash!=record['annotation_sha256']:
            raise ValueError('Annotation revision hash mismatch')
        if (row['revision'] != record['revision'] or annotation['split'] != 'val'
                or annotation['role'] != role or annotation['status'] != 'reviewed'
                or annotation['completeness'] != 'all_visible_instances' or annotation['ignore_regions']):
            raise ValueError('Evaluation requires frozen complete reviewed annotations')
        members = [n for n in files if n.startswith(f'{role}/images/val/') and Path(n).stem == image_id]
        if len(members) != 1:
            raise ValueError('Missing or duplicate exported image')
        name = members[0]
        if '..' in Path(name).parts or Path(name).is_absolute():
            raise ValueError('Unsafe export member')
        if sha256(export/name) != files[name] or files[name] != record['source_sha256'] or row['source']['sha256'] != files[name]:
            raise ValueError('Source hash mismatch')
        # Exported media may be immutable producer-owned symlinks. Never copy labels.
        config_name = f'{role}/data.yaml'
        if sha256(export/config_name) != files[config_name]:
            raise ValueError('Class mapping hash mismatch')
        names = json.loads((export/config_name).read_text())['names']
        truth = [{'label': names[str(b['class_id'])], 'box': b['xyxy_px']} for b in annotation['boxes']]
        selected.append({'record': record, 'row': row, 'path': export/name, 'truth': truth})
    if not selected:
        raise ValueError('No validation records')
    return receipt, selected
