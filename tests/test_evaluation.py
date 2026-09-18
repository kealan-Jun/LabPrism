import pytest
import json
import hashlib
from labprism.artifacts import sha256
from labprism.evaluation import counts, load_validation, match_detections, summarize


def box(label='beaker', confidence=.9, xyxy=None):
    return {'label': label, 'confidence': confidence, 'box': xyxy or [0, 0, 10, 10]}


def test_duplicates_and_wrong_classes_cannot_inflate_recall():
    predictions = [box(confidence=.4), box(confidence=.9), box('balance')]
    result, matches = counts(predictions, [box()])
    assert matches == [{'prediction': 1, 'truth': 0, 'iou': 1.0}]
    assert result['beaker'] == {'tp': 1, 'fp': 1, 'fn': 0}
    assert result['balance'] == {'tp': 0, 'fp': 1, 'fn': 0}
    assert summarize([result])['micro']['precision'] == pytest.approx(1/3)


def test_no_overlap_and_empty_predictions_preserve_false_negatives():
    assert not match_detections([box(xyxy=[20, 20, 30, 30])], [box()])
    result, _ = counts([], [box()])
    assert summarize([result])['micro'] == {'tp': 0, 'fp': 0, 'fn': 1, 'precision': None, 'recall': 0}


@pytest.mark.parametrize('failure',['incomplete','revision','media','snapshot','sealed_only','annotation_hash','duplicate','gate'])
def test_evaluation_rejects_untrusted_or_ineligible_export(tmp_path,failure):
    image=tmp_path/'first_person/images/val/a.jpg';image.parent.mkdir(parents=True);image.write_bytes(b'producer media')
    config=tmp_path/'first_person/data.yaml';config.write_text(json.dumps({'names':{'0':'beaker'}}))
    annotation={'split':'val','role':'first_person','status':'reviewed','completeness':'all_visible_instances','ignore_regions':[],'boxes':[]}
    if failure=='incomplete':annotation['completeness']='partial'
    row={'id':'a','revision':1,'source':{'sha256':sha256(image)},'annotation':annotation}
    snapshot=tmp_path/'annotations.json';snapshot.write_text(json.dumps({'images':[row]}))
    files={str(p.relative_to(tmp_path)):sha256(p) for p in [image,config,snapshot]}
    digest=hashlib.sha256(json.dumps(annotation,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    record={'image_id':'a','role':'first_person','split':'val','revision':1,'source_sha256':sha256(image),'annotation_sha256':digest}
    if failure=='revision':record['revision']=2
    if failure=='sealed_only':record['split']='test'
    if failure=='annotation_hash':record['annotation_sha256']='0'*64
    (tmp_path/'receipt.json').write_text(json.dumps({'schema_version':'annotation-workbench-yolo-export/1','files':files,'records':[record,record] if failure=='duplicate' else [record],'check':{'export_ready':failure!='gate','integrity_valid':True}}))
    if failure=='media':image.write_bytes(b'mutated')
    if failure=='snapshot':snapshot.write_text('{}')
    with pytest.raises(ValueError):load_validation(tmp_path)
