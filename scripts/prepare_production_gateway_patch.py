"""Prepare guarded gateway mount and rollback JSON patches from live JSON."""
import copy
import json
import pathlib
import sys

source, forward, rollback = map(pathlib.Path, sys.argv[1:4])
obj = json.loads(source.read_text(encoding='utf-8-sig'))
if obj['metadata']['name'] != 'maintenance-nginx' or obj['metadata']['namespace'] != 'core-omero-prod':
    raise ValueError('Unexpected gateway')
spec = obj['spec']['template']['spec']
if len(spec['containers']) != 1 or spec['containers'][0]['name'] != 'maintenance-nginx':
    raise ValueError('Unexpected gateway container')
volumes = spec['volumes']
mounts = spec['containers'][0]['volumeMounts']
if any(v['name'] == 'dashboard-gateway-config' for v in volumes):
    raise ValueError('Gateway candidate volume already exists')
new_volumes = copy.deepcopy(volumes) + [{'name': 'dashboard-gateway-config', 'configMap': {'defaultMode': 420, 'name': 'dashboard-production-gateway'}}]
new_mounts = copy.deepcopy(mounts) + [{'name': 'dashboard-gateway-config', 'mountPath': '/etc/nginx/conf.d/default.conf', 'subPath': 'default.conf', 'readOnly': True}]
vpath = '/spec/template/spec/volumes'
mpath = '/spec/template/spec/containers/0/volumeMounts'
def changes(before_v, before_m, after_v, after_m):
    return [{'op': 'test', 'path': vpath, 'value': before_v}, {'op': 'test', 'path': mpath, 'value': before_m},
            {'op': 'replace', 'path': vpath, 'value': after_v}, {'op': 'replace', 'path': mpath, 'value': after_m}]
forward.write_text(json.dumps(changes(volumes, mounts, new_volumes, new_mounts), indent=2), encoding='utf-8')
rollback.write_text(json.dumps(changes(new_volumes, new_mounts, volumes, mounts), indent=2), encoding='utf-8')
print('Prepared guarded gateway and rollback patches.')
