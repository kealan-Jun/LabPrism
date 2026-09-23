"""Keep model comparisons symmetric at the real duplicate-suppression boundary."""
import json
from pathlib import Path
import sys

from PIL import Image

from scripts.compare_engine_handoff import main


def test_baseline_and_candidate_both_use_runtime_suppression(tmp_path, monkeypatch):
    import annotation_workbench.storage

    # This fixture contains generated test pixels, not a NAS training export.
    monkeypatch.setattr(annotation_workbench.storage, 'volume', lambda _: None)
    dataset = tmp_path / 'dataset'
    images = dataset / 'first_person/images/val'
    images.mkdir(parents=True)
    Image.new('RGB', (200, 200)).save(images / 'test.jpg')
    truth = [{'class_id': 0, 'xyxy_px': [10, 10, 50, 50]}]
    hit = dict(truth[0], confidence=.9)
    duplicate = dict(class_id=0, xyxy_px=[11, 11, 51, 51], confidence=.8)
    false_positive = dict(class_id=0, xyxy_px=[100, 100, 150, 150], confidence=.8)

    def model(predictions):
        return dict(backend='TensorRT', ontology={'0': 'balance'},
                    thresholds={'0.25': {'micro': {'tp': 1, 'fp': 1, 'fn': 0}}},
                    rows=[dict(image_id='test', predictions=predictions, truth=truth)])

    root = tmp_path / 'pool/bulk-annotation-v1'
    job = root / 'training-v2/first_person'
    report = job / 'static-engine-candidate-640/report.json'
    report.parent.mkdir(parents=True)
    report.write_text(json.dumps(dict(iou=.7, reports={
        'service_engine': model([hit, duplicate]),
        'candidate_engine': model([hit, false_positive]),
    })))
    (job / 'request.json').write_text(json.dumps({'dataset': str(dataset)}))
    monkeypatch.setattr(sys, 'argv', [str(Path(__file__)), '--pool', str(root.parent),
                                    '--workbench', str(tmp_path), '--roles', 'first_person'])
    main()
    result = json.loads((root / 'runtime-acceptance-v2/fine-engine-report.json').read_text())['first_person']
    assert result['old_counts'] == {'tp': 1, 'fp': 0, 'fn': 0}
    assert result['candidate_counts'] == {'tp': 1, 'fp': 1, 'fn': 0}
    assert result['baseline_removed'] == 1
    assert len(result['rows'][0]['baseline_predictions']) == 1
    assert result['both_models_postprocessed'] is True
