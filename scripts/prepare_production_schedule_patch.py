"""Prepare a guarded production dashboard-only scheduler cutover patch."""
import json
import pathlib
import sys

source, destination = map(pathlib.Path, sys.argv[1:3])
cronjob = json.loads(source.read_text(encoding='utf-8-sig'))
if cronjob['metadata']['name'] != 'service-schedule' or cronjob['metadata']['namespace'] != 'core-omero-prod':
    raise ValueError('Unexpected production scheduler')
containers = cronjob['spec']['jobTemplate']['spec']['template']['spec']['containers']
if len(containers) != 1 or containers[0]['name'] != 'scheduler':
    raise ValueError('Unexpected scheduler container')
original = containers[0]['args'][0]
old = '''  ensure_scale dashboard 1
  oc rollout status deployment/dashboard -n core-omero-prod --timeout=10m'''
new = '''  dashboard_replicas=$(oc get deployment dashboard-django -n "$NAMESPACE" -o jsonpath='{.spec.replicas}')
  if [ "$dashboard_replicas" -eq 0 ]; then
    ensure_scale dashboard-django 1
  else
    echo "dashboard-django: already running with $dashboard_replicas replica(s)"
  fi
  oc rollout status deployment/dashboard-django -n core-omero-prod --timeout=10m'''
down_old = '  ensure_scale dashboard 0'
down_new = '  ensure_scale dashboard-django 0'
if original.count(old) != 1 or original.count(down_old) != 1:
    raise ValueError('Live dashboard branch differs from reviewed version')
updated = original.replace(old, new).replace(down_old, down_new)
path = '/spec/jobTemplate/spec/template/spec/containers/0/args/0'
destination.write_text(json.dumps([{'op': 'test', 'path': path, 'value': original},
                                   {'op': 'replace', 'path': path, 'value': updated}], indent=2), encoding='utf-8')
print('Prepared guarded production scheduler patch.')
