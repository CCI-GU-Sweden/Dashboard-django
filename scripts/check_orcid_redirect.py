"""Check the deployed login starts the sandbox OAuth flow; no credentials needed."""
from html.parser import HTMLParser
from http.cookiejar import CookieJar
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import HTTPCookieProcessor, HTTPRedirectHandler, Request, build_opener

base = 'https://dashboard-django-test.apps.k8s.gu.se'


class FormParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.token = None

    def handle_starttag(self, tag, attrs):
        data = dict(attrs)
        if tag == 'input' and data.get('name') == 'csrfmiddlewaretoken':
            self.token = data.get('value')


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


opener = build_opener(HTTPCookieProcessor(CookieJar()), NoRedirect())
with opener.open(base + '/', timeout=20) as response:
    form = FormParser()
    form.feed(response.read().decode('utf-8'))
if not form.token:
    raise RuntimeError('No CSRF token found on the login page.')
request = Request(base + '/accounts/orcid/login/', data=urlencode({'csrfmiddlewaretoken': form.token}).encode(), headers={'Referer': base + '/'}, method='POST')
try:
    opener.open(request, timeout=20)
    raise RuntimeError('Expected a redirect to ORCID.')
except HTTPError as response:
    if response.code != 302:
        raise
    target = urlparse(response.headers['Location'])
    params = parse_qs(target.query)
    expected_callback = base + '/accounts/orcid/login/callback/'
    if target.scheme != 'https' or target.netloc != 'sandbox.orcid.org' or params.get('redirect_uri') != [expected_callback] or not params.get('state'):
        raise RuntimeError('The ORCID destination, callback, or state is incorrect.')
    print('ORCID sandbox authorization redirect, callback, and state: OK')
