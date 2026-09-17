import importlib.util
import json
from pathlib import Path
import pytest
spec=importlib.util.spec_from_file_location("publish",Path(__file__).parents[1]/"scripts/publish_local_release.py")
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)

@pytest.mark.parametrize("fstype,volume",[("ext4",p.EXPECTED_VOLUME),("autofs",p.EXPECTED_VOLUME),("cifs","wrong-volume")])
def test_refuses_unmounted_or_wrong_volume(tmp_path,monkeypatch,fstype,volume):
    (tmp_path/".labprism-volume.json").write_text(json.dumps({"project":"LabPrism","volume_id":volume}))
    monkeypatch.setattr(p.subprocess,"check_output",lambda *a,**kw:json.dumps({"filesystems":[{"fstype":fstype,"target":str(tmp_path)}]}))
    with pytest.raises(ValueError):p.verify_nas(tmp_path)
