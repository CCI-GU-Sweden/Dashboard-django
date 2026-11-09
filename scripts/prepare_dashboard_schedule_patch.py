"""Prepare a guarded patch from the live service-schedule CronJob JSON.

The JSON patch tests the exact old script before replacing it, so a concurrent
operator change cannot be overwritten silently. Inspect output before use.
"""
import json
import pathlib
import sys

source, destination = map(pathlib.Path, sys.argv[1:3])
cronjob = json.loads(source.read_text(encoding='utf-8-sig'))
if cronjob['metadata']['name'] != 'service-schedule':
    raise ValueError('Unexpected CronJob')
containers = cronjob['spec']['jobTemplate']['spec']['template']['spec']['containers']
if len(containers) != 1 or containers[0]['name'] != 'scheduler':
    raise ValueError('Unexpected scheduler container')
original = containers[0]['args'][0]
old = '''  ensure_scale dashboard-test 1
  oc rollout status deployment/dashboard-test -n core-omero-test --timeout=10m'''
new = '''  dashboard_replicas=$(oc get deployment dashboard-django -n "$NAMESPACE" -o jsonpath='{.spec.replicas}')
  if [ "$dashboard_replicas" -eq 0 ]; then
    ensure_scale dashboard-django 1
  else
    echo "dashboard-django: already running with $dashboard_replicas replica(s)"
  fi
  oc rollout status deployment/dashboard-django -n core-omero-test --timeout=10m'''
down_old = '  ensure_scale dashboard-test 0'
down_new = '  ensure_scale dashboard-django 0'
if original.count(old) != 1 or original.count(down_old) != 1:
    raise ValueError('Live dashboard scheduler differs from the reviewed version')
updated = original.replace(old, new).replace(down_old, down_new)
path = '/spec/jobTemplate/spec/template/spec/containers/0/args/0'
patch = [{'op': 'test', 'path': path, 'value': original},
         {'op': 'replace', 'path': path, 'value': updated}]
destination.write_text(json.dumps(patch, indent=2), encoding='utf-8')
print(f'Prepared guarded scheduler patch: {destination}')
