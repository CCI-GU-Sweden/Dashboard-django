"""Check the ORCID authorization redirect through an internal gateway canary."""
import re
import sys
from urllib.parse import parse_qs, urlparse

import requests

gateway = sys.argv[1]
host = sys.argv[2]
base = f'http://{gateway}:3000'
headers = {'Host': host, 'X-Forwarded-Proto': 'https',
           'Origin': f'https://{host}', 'Referer': f'https://{host}/'}
session = requests.Session()
page = session.get(base + '/', headers=headers, timeout=10)
page.raise_for_status()
match = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)', page.text)
if not match:
    raise RuntimeError('Sign-in form not found')
# The canary is reached over internal HTTP. A browser reaches the Route over
# HTTPS and sends Secure cookies automatically; emulate that for this test.
headers['Cookie'] = '; '.join(f'{cookie.name}={cookie.value}' for cookie in session.cookies)
response = session.post(base + '/accounts/orcid/login/', headers=headers,
                        data={'csrfmiddlewaretoken': match.group(1)},
                        allow_redirects=False, timeout=10)
redirect = urlparse(response.headers.get('Location', ''))
callback = parse_qs(redirect.query).get('redirect_uri', [''])[0]
expected = f'https://{host}/accounts/orcid/login/callback/'
if response.status_code != 302 or redirect.hostname != 'orcid.org' or callback != expected:
    raise RuntimeError(f'Unexpected login redirect: status={response.status_code}, host={redirect.hostname}, callback={callback}')
print(f'Gateway and production ORCID redirect verified; callback: {callback}')
