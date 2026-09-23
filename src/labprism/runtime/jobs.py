"""Durable single-GPU local jobs; failed attempts are retained and explicitly retried."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import threading
import uuid

from labprism.artifacts import sha256
from labprism.perception.display_video import load_recipe
from labprism.runtime.observation import seal_observation, verify_observation

MAX_UPLOAD = 1024 ** 3


def write_json(path, value):
    path = Path(path)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2))
    temporary.replace(path)


class Jobs:
    def __init__(self, root, project, publish, *, start_worker=True):
        self.root, self.project, self.publish = Path(root), Path(project), publish
        self.folder = self.root / 'jobs'
        self.folder.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.queue = queue.Queue()
        self.items = {}
        for path in self.folder.glob('*/job.json'):
            item = json.loads(path.read_text())
            if item['state'] in {'queued', 'running', 'publishing'}:
                item.update(state='failed', error='服务重新启动，前一次处理已中断；可重新分析，旧记录保留。')
                write_json(path, item)
            self.items[item['id']] = item
        if start_worker:
            threading.Thread(target=self._worker, daemon=True, name='labprism-gpu-jobs').start()

    def settings(self):
        config = json.loads((self.root / 'receipts/local-analysis.json').read_text())
        recipe = Path(config['recipe']).resolve()
        python = Path(config['python']).resolve()
        if not recipe.is_relative_to(self.root.resolve()) or not python.is_file():
            raise ValueError('分析环境未配置')
        load_recipe(recipe)
        return config

    def sources(self):
        sources = []
        for receipt in sorted((self.root / 'observations').glob('*/receipt.json')):
            if not re.fullmatch(r'[a-z0-9-]+', receipt.parent.name) or receipt.parent.is_symlink():
                continue
            data = json.loads(receipt.read_text())
            sources.append({'id': receipt.parent.name, 'title': data.get('title', receipt.parent.name),
                            'camera_role': data['camera_role'], 'camera_id': data['camera_id']})
        return sources

    def list(self):
        with self.lock:
            return [{k: v for k, v in item.items() if k in {
                'id', 'title', 'state', 'created_at', 'progress', 'frames', 'timestamp_ms',
                'duration_ms', 'error', 'result_url', 'retry_of'}}
                for item in sorted(self.items.values(), key=lambda j: j['created_at'], reverse=True)]

    def accept_upload(self, stream, length, metadata):
        if not 0 < length <= MAX_UPLOAD:
            raise ValueError('视频文件须小于 1 GiB')
        self.settings()
        self._capacity()
        directory = self.root / 'observations' / f'upload-{uuid.uuid4().hex}'
        directory.mkdir(parents=True)
        try:
            with (directory / 'clip.mp4').open('xb') as output:
                remaining = length
                while remaining:
                    block = stream.read(min(1024 * 1024, remaining))
                    if not block:
                        raise ValueError('视频上传中断，请重试')
                    output.write(block)
                    remaining -= len(block)
            seal_observation(directory, metadata)
            return self.submit(directory.name)
        except Exception:
            # Only an unsealed failed intake is disposable; accepted source
            # bytes and failed inference evidence are retained.
            if not (directory / 'receipt.json').exists():
                shutil.rmtree(directory)
            raise

    def _capacity(self):
        with self.lock:
            if sum(i['state'] in {'queued', 'running', 'publishing'} for i in self.items.values()) >= 8:
                raise ValueError('当前队列已满，请等待已有分析完成')

    def submit(self, source_id, retry_of=None):
        config = self.settings()
        if source_id not in {s['id'] for s in self.sources()}:
            raise ValueError('未知视频来源')
        media = self.root / 'observations' / source_id
        receipt = verify_observation(media)
        with self.lock:
            self._capacity()
            identifier = 'analysis-' + uuid.uuid4().hex
            directory = self.folder / identifier
            directory.mkdir()
            shutil.copyfile(config['recipe'], directory / 'recipe.json')
            item = dict(id=identifier, title=receipt['title'], created_at=datetime.now(timezone.utc).isoformat(),
                        state='queued', progress=0, frames=0, source_id=source_id, retry_of=retry_of,
                        recipe_sha256=sha256(directory / 'recipe.json'), python=config['python'])
            self.items[identifier] = item
            write_json(directory / 'job.json', item)
            self.queue.put(identifier)
            return {'id': identifier}

    def retry(self, identifier):
        with self.lock:
            old = self.items.get(identifier)
            if not old or old['state'] != 'failed':
                raise ValueError('仅失败的处理可以重试')
            return self.submit(old['source_id'], retry_of=identifier)

    def _update(self, identifier, **fields):
        with self.lock:
            self.items[identifier].update(fields)
            write_json(self.folder / identifier / 'job.json', self.items[identifier])

    def _worker(self):
        while True:
            identifier = self.queue.get()
            directory = self.folder / identifier
            item = self.items[identifier]
            run = self.root / 'runs' / identifier
            try:
                self._update(identifier, state='running')
                if sha256(directory / 'recipe.json') != item['recipe_sha256']:
                    raise ValueError('冻结的分析配置已变化')
                command = [item['python'], '-m', 'labprism.perception.display_video',
                           str(self.root / 'observations' / item['source_id']), str(run),
                           '--recipe', str(directory / 'recipe.json')]
                environment = {**os.environ, 'PYTHONPATH': str(self.project / 'src'), 'PYTHONUNBUFFERED': '1'}
                with (directory / 'worker.log').open('w') as log:
                    process = subprocess.Popen(command, cwd=self.project, env=environment, stdout=subprocess.PIPE,
                                               stderr=subprocess.STDOUT, text=True)
                    for line in process.stdout:
                        log.write(line)
                        log.flush()
                        try:
                            progress = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if progress.get('stage') == 'running':
                            self._update(identifier, **{k: progress[k] for k in ['progress', 'frames', 'timestamp_ms', 'duration_ms']})
                        elif progress.get('stage') == 'complete':
                            self._update(identifier, frames=progress['metrics']['processed_frames'], progress=1)
                    if process.wait():
                        raise RuntimeError('GPU 视频分析失败，运行日志已保留；可在资源可用后重新分析。')
                self._update(identifier, state='publishing', progress=1)
                self.publish({'id': identifier, 'title': item['title'] + ' · 显示窗候选', 'run': str(run),
                              'review_note': '新视频实际 GPU 分析；候选未晋级，其他任务未执行。'})
                self._update(identifier, state='complete', result_url=f'demo.html?clip={identifier}')
            except Exception as error:
                self._update(identifier, state='failed', error=str(error)[:400])
            finally:
                self.queue.task_done()
