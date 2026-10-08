"""Read published workpaper/model deliveries by their project-scoped manifest."""
import hashlib
import json
import re


def delivery_manifest(root,project,identifier):
    if not re.fullmatch(r'[a-f0-9]{32}',identifier):return None
    folder=root/'research'/project/'deliveries'/identifier
    manifest=folder/'delivery.json'
    return (folder,json.loads(manifest.read_text(encoding='utf-8'))) if manifest.is_file() else None


def delivery_path(delivery,name):
    folder,manifest=delivery
    listed=next((f for f in manifest['files'] if f['name']==name),None)
    if listed is None:raise ValueError('交付中没有此文件；可用文件：'+', '.join(f['name'] for f in manifest['files']))
    path=folder/name
    if path.resolve().parent!=folder.resolve():raise ValueError('交付文件路径越界')
    data=path.read_bytes()
    if len(data)!=listed['size'] or hashlib.sha256(data).hexdigest()!=listed['sha256']:
        raise ValueError('交付文件与清单不一致')
    return path
