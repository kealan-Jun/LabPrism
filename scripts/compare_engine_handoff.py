"""Apply the producer's existing suppression to pinned development predictions."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--pool', type=Path, required=True)
    parser.add_argument('--workbench', type=Path, required=True)
    parser.add_argument('--first-person-run', default='training-v2')
    parser.add_argument('--third-person-run', default='training-v2')
    parser.add_argument('--output-name', default='runtime-acceptance-v2')
    args = parser.parse_args()
    sys.path.insert(0, str(args.workbench))
    from annotation_workbench.bulk_model_comparison import measure
    from annotation_workbench.storage import volume
    from visioncortex.detection_duplicates import suppress_duplicate_boxes
    from visioncortex.schemas import BoxEvidence
    from PIL import Image, ImageDraw
    volume(args.pool)
    root = args.pool / 'bulk-annotation-v1'
    output = root / args.output_name
    output.mkdir(exist_ok=False)
    summaries = {}
    for role, threshold in [('first_person', .55), ('third_person', .7)]:
        version = args.first_person_run if role == 'first_person' else args.third_person_run
        job = root / version / role
        report_path = job / 'static-engine-candidate-640/report.json'
        report = json.loads(report_path.read_text())
        training = json.loads((job / 'request.json').read_text())
        images = Path(training['dataset']) / role / 'images/val'
        names = report['reports']['candidate_engine']['ontology']
        counts, classes, rows = Counter(), defaultdict(Counter), []
        for old, row in zip(report['reports']['service_engine']['rows'], report['reports']['candidate_engine']['rows'], strict=True):
            if old['image_id'] != row['image_id'] or old['truth'] != row['truth']:
                raise ValueError('Model comparison uses different validation inputs or labels')
            path = next(p for p in images.glob(row['image_id'] + '.*') if p.suffix.lower() in {'.jpg', '.jpeg', '.png'})
            with Image.open(path) as original:
                image = original.convert('RGB')
            width, height = image.size
            predictions = [p for p in row['predictions'] if p['confidence'] >= .25]
            boxes = [BoxEvidence(class_id=p['class_id'], class_name=names[str(p['class_id'])], confidence=p['confidence'], xyxy_norm=tuple(v / (width if i % 2 == 0 else height) for i, v in enumerate(p['xyxy_px']))) for p in predictions]
            _, audit = suppress_duplicate_boxes(boxes, threshold)
            retained = [predictions[i] for i in audit.retained_input_indices]
            for category, value in measure(retained, row['truth']).items():
                counts.update(value)
                classes[names[str(category)]].update(value)
            rows.append(dict(image_id=row['image_id'], image_path=str(path), image_sha256=hashlib.sha256(path.read_bytes()).hexdigest(), predictions=retained, raw_count=len(predictions), removed=len(audit.removals), truth=row['truth']))
            if role == 'first_person' and (row['image_id'] in {'F071', 'F123'} or any(p['class_id'] == 15 for p in row['truth'])):
                comparison = Image.new('RGB', (1600, 640), '#122922')
                for column, (title, values) in enumerate([('SERVICE ENGINE', [p for p in old['predictions'] if p['confidence'] >= .25]), ('CANDIDATE ENGINE + EXISTING NMS', retained)]):
                    panel = image.copy()
                    draw = ImageDraw.Draw(panel)
                    for prediction in values:
                        xy = prediction['xyxy_px']
                        draw.rectangle(xy, outline='#c9f54d', width=3)
                        draw.text((xy[0] + 3, xy[1] + 3), names[str(prediction['class_id'])], fill='white', stroke_width=2, stroke_fill='#122922')
                    panel.thumbnail((800, 600))
                    comparison.paste(panel, (column * 800, 30))
                    ImageDraw.Draw(comparison).text((column * 800 + 10, 8), title, fill='white')
                comparison.save(output / (role + '-' + row['image_id'] + '.jpg'))
        summaries[role] = dict(source_report=str(report_path), source_report_sha256=hashlib.sha256(report_path.read_bytes()).hexdigest(), confidence=.25, predict_iou=.7, duplicate_suppression_iou=threshold, old_counts=report['reports']['service_engine']['thresholds']['0.25']['micro'], candidate_counts=dict(counts), candidate_classes={k: dict(v) for k, v in classes.items()}, rows=rows)
        print(role, summaries[role]['old_counts'], dict(counts))
    (output / 'fine-engine-report.json').write_text(json.dumps(summaries, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
