import subprocess

from labprism.perception.baseline import source_revision


def test_archive_does_not_inherit_invocation_directory_git(tmp_path):
    # pytest is running inside a Git checkout, but the source archive is not one.
    assert source_revision(tmp_path) == {'git_commit':None,'git_dirty':None}


def test_source_checkout_identity_and_dirty_state(tmp_path):
    subprocess.run(['git','init','-q',str(tmp_path)],check=True)
    subprocess.run(['git','-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','--allow-empty','-qm','fixture'],cwd=tmp_path,check=True)
    expected=subprocess.check_output(['git','rev-parse','HEAD'],cwd=tmp_path,text=True).strip()
    assert source_revision(tmp_path)=={'git_commit':expected,'git_dirty':False}
    (tmp_path/'local-change').write_text('fixture')
    assert source_revision(tmp_path)=={'git_commit':expected,'git_dirty':True}
