"""Keep the dashboard shell usable on networks that block third-party CDNs."""
from html.parser import HTMLParser
from pathlib import Path
import re

from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.contrib.staticfiles import finders
from django.template.loader import get_template
from django.test import SimpleTestCase


class AssetParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.assets = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ('script', 'img') and attrs.get('src'):
            self.assets.append(attrs['src'])
        if tag == 'link' and attrs.get('href'):
            self.assets.append(attrs['href'])


class LocalAssetTests(SimpleTestCase):
    def test_dashboard_shell_loads_only_local_assets(self):
        parser = AssetParser()
        parser.feed(get_template('base.html').render({'user': AnonymousUser()}))
        self.assertIn('/static/vendor/bulma/bulma.min.css', parser.assets)
        self.assertTrue(all(url.startswith('/static/') for url in parser.assets), parser.assets)
        self.assertTrue(finders.find('vendor/bulma/bulma.min.css'))

    def test_vendored_bulma_has_no_external_dependencies(self):
        css = (Path(settings.BASE_DIR) / 'static/vendor/bulma/bulma.min.css').read_text(encoding='utf-8')
        self.assertIn('bulma.io v0.9.4', css[:500])
        self.assertNotRegex(css, re.compile(r'@import|url\(\s*["\']?(?:https?:)?//', re.IGNORECASE))
