"""Insert registered originals locally; never mutate provider output or its ledger."""
from pathlib import Path
import hashlib
from PIL import Image, ImageOps
from shape_masks import boundary_mask


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def compose(project, provider_file, originals):
    project = Path(project)
    with Image.open(project / provider_file) as source:
        result = source.convert('RGB')
    for item in originals:
        box = item['box']
        clear = item.get('clearBox')
        if clear:
            cx, cy, cw, ch = [round(clear[k] * scale) for k, scale in
                             [('x',result.width),('y',result.height),('w',result.width),('h',result.height)]]
            if cx < 0 or cy < 0 or cw <= 0 or ch <= 0 or cx+cw > result.width or cy+ch > result.height:
                raise ValueError('原预留框清理区域超出画布')
            result.paste(Image.new('RGB',(cw,ch),item.get('background','#FFFFFF')),(cx,cy))
        x, y, w, h = [round(box[k] * scale) for k, scale in
                       [('x', result.width), ('y', result.height),
                        ('w', result.width), ('h', result.height)]]
        if w <= 0 or h <= 0 or x < 0 or y < 0 or x+w > result.width or y+h > result.height:
            raise ValueError('原图插入框超出画布或尺寸无效')
        if item.get('fit') != 'contain':
            raise ValueError('完整预览原图必须用 contain 等比保留原图，仅按登记 boundaryMask 裁切显示边缘')
        with Image.open(project / item['path']) as source:
            rgba = ImageOps.exif_transpose(source).convert('RGBA')
            photo = Image.new('RGBA', rgba.size, 'white')
            photo.alpha_composite(rgba)
            inset = ImageOps.contain(photo.convert('RGB'), (w, h), Image.Resampling.LANCZOS)
        tile = Image.new('RGB', (w, h), item.get('background', '#FFFFFF'))
        tile.paste(inset, ((w-inset.width)//2, (h-inset.height)//2))
        mask = item.get('boundaryMask')
        result.paste(tile, (x, y), boundary_mask(mask, (w, h)) if mask else None)
    return result


def insertion_errors(project, page, plan, record=None):
    project = Path(project)
    prefix = str(page.get('id', '?'))
    provider = page.get('providerFile')
    originals = page.get('originals')
    if not provider or not page.get('providerSha256') or originals is None:
        return [f'{prefix} 尚未登记原图插入：需要 providerFile、providerSha256 与 originals']
    if not (project / provider).is_file():
        return [f'{prefix} AI 原始页缺失：{provider}']
    errors = []
    actual_provider_hash = sha(project / provider)
    if actual_provider_hash != page['providerSha256']:
        errors.append(f'{prefix} AI 原始页哈希已变化')
    if record and (record.get('output') != provider or record.get('sha256') != actual_provider_hash):
        errors.append(f'{prefix} AI 原始页与真实生成账本不一致')
    planned = {item['id']: item for item in (plan or {}).get('images', [])}
    if len(originals) != len(planned) or {item.get('imageId') for item in originals} != set(planned):
        errors.append(f'{prefix} 原图插入数量或编号与图片计划不一致')
    for item in originals:
        image = planned.get(item.get('imageId'))
        if not image:
            continue
        if item.get('path') != image.get('path') or item.get('sourceId') != image.get('sourceId'):
            errors.append(f'{prefix} {item.get("imageId")} 原图来源与登记计划不一致')
        source = project / str(item.get('path', ''))
        if not source.is_file() or sha(source) != item.get('sha256'):
            errors.append(f'{prefix} {item.get("imageId")} 原图缺失或哈希已变化')
        if item.get('box') != image.get('box'):
            errors.append(f'{prefix} {item.get("imageId")} 插入框与图片计划不一致')
        if item.get('boundaryMask') != image.get('boundaryMask'):
            errors.append(f'{prefix} {item.get("imageId")} 边缘裁切轮廓与图片计划不一致')
        if item.get('clearBox'):
            clear=item['clearBox']; box=item.get('box') or {}
            if any(clear.get(k,0) > box.get(k,0)+.001 for k in ('x','y')) or any(clear.get(k,0)+clear.get(dim,0)+.001 < box.get(k,0)+box.get(dim,0) for k,dim in [('x','w'),('y','h')]):
                errors.append(f'{prefix} 原预留框清理区域必须完整包含原图插入框')
        if item.get('fit') != 'contain':
            errors.append(f'{prefix} 原图必须等比适配，仅按登记 boundaryMask 裁切显示边缘')
    if not errors:
        try:
            expected = compose(project, provider, originals)
            with Image.open(project / page['file']) as opened:
                actual = opened.convert('RGB')
            if actual.size != expected.size or actual.tobytes() != expected.tobytes():
                errors.append(f'{prefix} 最终预览未按登记记录插入原图，或插入后的页面被修改')
        except (OSError, ValueError, KeyError, TypeError) as exc:
            errors.append(f'{prefix} 原图插入验证失败：{exc}')
    return errors


def insert_pages(project):
    import json
    project = Path(project)
    manifest_path = project / '04_full-preview/previews.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    plans = {s['id']: s for s in json.loads((project / '02_design/image-plan.json').read_text(encoding='utf-8'))['slides']}
    ledger = json.loads((project / '04_full-preview/generation-ledger.json').read_text(encoding='utf-8'))['jobs']
    updates = []
    for page in manifest['pages']:
        record = ledger[page['jobId']]
        if record.get('status') != 'complete':
            raise ValueError(f'{page["id"]} AI 生成尚未完成')
        provider = record['output']
        if sha(project / provider) != record['sha256']:
            raise ValueError(f'{page["id"]} AI 原始页哈希不一致')
        originals = [{'imageId': image['id'], 'sourceId': image['sourceId'],
                      'path': image['path'], 'sha256': sha(project / image['path']),
                      'box': image['box'], 'fit': 'contain', 'background': '#FFFFFF'}
                     for image in plans.get(page['id'], {}).get('images', [])]
        for item, image in zip(originals, plans.get(page['id'], {}).get('images', [])):
            if image.get('boundaryMask'):
                item['boundaryMask'] = image['boundaryMask']
            placeholder=next((p for p in page.get('placeholders',[]) if p.get('imageId')==item['imageId']),None)
            if placeholder and placeholder.get('clearBox'):
                item['clearBox']=placeholder['clearBox']
        out = project / '04_full-preview/slides' / (page['id']+'.png')
        if out.resolve() == (project / provider).resolve():
            raise ValueError('禁止覆盖 AI 原始输出；slides 必须与 provider assets 分开')
        updates.append((page, provider, originals, out, compose(project, provider, originals)))
    for page, provider, originals, out, result in updates:
        out.parent.mkdir(parents=True, exist_ok=True)
        result.save(out)
        page.update(file=out.relative_to(project).as_posix(), sha256=sha(out),
                    providerFile=provider, providerSha256=sha(project / provider), originals=originals)
        page['review'] = ''  # Re-insertion requires actual visual review of the final composite.
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


if __name__ == '__main__':
    import argparse
    from workflow_lib import project_lock
    parser = argparse.ArgumentParser(description='完整预览：本地插入登记原图，再逐页实际检查')
    parser.add_argument('project', type=Path)
    args = parser.parse_args()
    with project_lock(args.project):
        insert_pages(args.project)
    print('原图已插入完整预览；请逐页实际查看并填写 review 后再 await 2.2。')
