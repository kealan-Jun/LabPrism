#!/usr/bin/env python3
"""Exercise the real local website and video predictions in installed Chrome."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright


def check_viewport(page):
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Horizontal overflow'


def inspect_overlay(page, result):
    rendered = page.locator('#overlay').evaluate('e => ({time:+e.dataset.presentationMs, frame:e.dataset.frameIndex})')
    frame = next(f for f in result['frames'] if str(f['frame_index']) == rendered['frame'])
    assert -.5 <= rendered['time']-frame['timestamp_ms'] <= 150, 'Future or stale prediction'
    boxes = page.locator('#overlay rect').evaluate_all('es => es.map(e => ["x","y","width","height"].map(k=>+e.getAttribute(k)))')
    assert len(boxes) == len(frame['objects'])
    for box, obj in zip(boxes, frame['objects']):
        x,y,x2,y2 = obj['box']
        assert all(abs(a-b) < .001 for a,b in zip(box, [x,y,x2-x,y2-y]))
    assert page.locator('#overlay circle').count() == 21*len(frame['hands'])
    return frame['frame_index']


def step(page, result, delta):
    page.wait_for_function('!document.getElementById("video").seeking')
    current_ms = page.locator('#video').evaluate('v=>v.currentTime*1000')
    index = max((i for i,f in enumerate(result['frames']) if f['timestamp_ms'] <= current_ms+.001), default=-1)
    target = result['frames'][max(0,min(len(result['frames'])-1,index+delta))]
    page.locator('#next' if delta > 0 else '#previous').click()
    page.wait_for_function('f => !document.getElementById("video").seeking && Math.abs(document.getElementById("video").currentTime*1000-f.timestamp_ms)<.1 && document.getElementById("overlay").dataset.frameIndex === String(f.frame_index)',arg=target)
    return inspect_overlay(page, result)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--url', default='http://127.0.0.1:8031/')
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    if urlparse(args.url).hostname not in {'127.0.0.1', 'localhost', '::1'}:
        raise ValueError('Private media checks require a loopback preview')
    args.output.mkdir(parents=True, exist_ok=False)
    report = {'schema_version':'labprism-browser-verification/1', 'created_at':datetime.now(timezone.utc).isoformat(),
              'url':args.url, 'checks':[], 'screenshots':[], 'quality_acceptance':False}
    errors = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=shutil.which('google-chrome') or shutil.which('chromium'), headless=True)
        report['browser'] = browser.version
        page = browser.new_page(viewport={'width':1440,'height':1000}, device_scale_factor=1)
        page.on('pageerror', lambda error:errors.append(str(error)))
        for width,height in [(1440,1000),(768,1024),(390,844),(320,800)]:
            page.set_viewport_size({'width':width,'height':height})
            for path in ['index.html','technology.html','demo.html']:
                response = page.goto(args.url+path)
                assert response.status == 200
                if path == 'demo.html':
                    page.wait_for_function('!document.getElementById("play").disabled')
                    page.locator('#next').click()
                    page.wait_for_function('document.getElementById("overlay").dataset.valid === "true"')
                check_viewport(page)
                if width in {1440,390}:
                    name = f'{width}-{path.removesuffix(".html")}.png'
                    page.screenshot(path=str(args.output/name), full_page=True)
                    report['screenshots'].append(name)
            report['checks'].append(f'three_pages_no_overflow_{width}')
        page.set_viewport_size({'width':1440,'height':1000})
        page.goto(args.url)
        page.get_by_role('navigation').get_by_role('link', name='技术能力').click()
        assert page.url.endswith('technology.html')
        page.get_by_role('navigation').get_by_role('link', name='演示空间').click()
        page.wait_for_function('!document.getElementById("play").disabled')
        catalog = page.request.get(args.url+'demo-data/catalog.json').json()
        for i,item in enumerate(catalog['clips']):
            page.locator('#clip-select').select_option(str(i))
            page.wait_for_function('!document.getElementById("play").disabled')
            result = page.request.get(args.url+item['result']).json()
            first = step(page, result, 1)
            assert step(page, result, 1) > first
            assert step(page, result, -1) == first
            current = next(f for f in result['frames'] if f['frame_index'] == first)
            page.locator('#original').check()
            assert page.locator('#overlay > *').count() == 0
            page.locator('#original').uncheck()
            inspect_overlay(page, result)
            page.locator('#masks').uncheck()
            assert page.locator('#overlay path').count() == 0
            page.locator('#masks').check()
            page.locator('#hands').uncheck()
            assert page.locator('#overlay circle').count() == 0
            page.locator('#hands').check()
            page.locator('#boxes').uncheck()
            assert page.locator('#overlay rect').count() == 0
            page.locator('#boxes').check()
            page.locator('#labels').check()
            assert page.locator('#overlay text').count() == len(current['objects'])
            page.locator('#labels').uncheck()
            if current['objects']:
                page.locator('#object-select').select_option('0')
                assert page.locator('#overlay rect').count() == 1
                assert '置信度' in page.locator('#instance-detail').inner_text()
                page.locator('#object-select').select_option('')
            page.locator('#speed').select_option('2')
            assert page.locator('#video').evaluate('v=>v.playbackRate') == 2
            page.locator('#play').focus()
            page.keyboard.press('Space')
            page.wait_for_function('document.getElementById("video").currentTime > 1')
            page.locator('#play').click()
            assert page.locator('#video').evaluate('v=>v.paused')
            inspect_overlay(page, result)
            page.locator('#checkpoints button').nth(2).click()
            page.wait_for_function('Math.abs(document.getElementById("video").currentTime-4)<.05 && !document.getElementById("video").seeking')
            inspect_overlay(page, result)
            with page.expect_download() as download:
                page.locator('#result-link').click()
            assert download.value.failure() is None
            name = f'clip-{item["id"]}.png'
            page.locator('.live-viewer').screenshot(path=str(args.output/name))
            report['screenshots'].append(name)
            report['checks'].append({'clip':item['id'],'play_pause_step_layers_details_seek_download':'passed'})
        # A failed switch must clear old predictions, evidence, links and controls.
        target = catalog['clips'][0]
        page.route('**/'+target['result'], lambda route:route.fulfill(status=503,body='temporarily unavailable'))
        page.locator('#clip-select').select_option('0')
        page.wait_for_function('document.getElementById("load-status").textContent.includes("503")')
        assert page.locator('#play').is_disabled()
        assert page.locator('#overlay > *').count() == 0
        assert page.locator('#evidence > *').count() == 0
        assert page.locator('#result-link').is_hidden()
        page.unroute('**/'+target['result'])
        page.locator('#clip-select').select_option('1')
        page.wait_for_function('!document.getElementById("play").disabled')
        assert page.locator('#video').evaluate('v=>v.playbackRate') == 2
        report['checks'].extend(['navigation','keyboard_play','failed_clip_clears_stale_state','clip_switch_preserves_speed'])
        assert not errors, errors
        report['page_errors'] = errors
        browser.close()
    report['status'] = 'passed'
    (args.output/'receipt.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':'passed','receipt':str(args.output/'receipt.json')}))


if __name__ == '__main__':
    main()
