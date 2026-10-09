"""Authorized HTTPS JSON feeds, pinned to a checked public DNS address for each request."""
import http.client, ipaddress, os, re, socket, ssl
from urllib.parse import urlsplit
from django.conf import settings
from .services import RuleError

def fetch_feed(source):
    u=urlsplit(source.url)
    if u.scheme!='https' or u.hostname not in settings.FEED_HOSTS or u.username or u.password or u.fragment or u.port not in (None,443):
        raise RuleError('Feed must use an explicitly approved HTTPS hostname on port 443.')
    addresses={a[4][0] for a in socket.getaddrinfo(u.hostname,443,type=socket.SOCK_STREAM)}
    if not addresses or any(not ipaddress.ip_address(a).is_global for a in addresses):raise RuleError('Feed DNS must resolve only to public addresses.')
    address=sorted(addresses)[0]
    class PinnedHTTPS(http.client.HTTPSConnection):
        def connect(self):
            raw=socket.create_connection((address,443),timeout=self.timeout)
            self.sock=self._context.wrap_socket(raw,server_hostname=self.host)
    headers={'Accept':'application/json','User-Agent':'ScoutDesk/1.0 authorized-feed-ingestion'}
    if source.token_env:
        if not re.fullmatch(r'SCOUT_FEED_[A-Z0-9_]+',source.token_env):raise RuleError('Feed credential names must start SCOUT_FEED_.')
        token=os.getenv(source.token_env,'')
        if not token:raise RuleError('Feed credential is not configured.')
        headers['Authorization']='Bearer '+token
    client=PinnedHTTPS(u.hostname,timeout=15,context=ssl.create_default_context())
    try:
        client.request('GET',(u.path or '/')+('?' + u.query if u.query else ''),headers=headers)
        response=client.getresponse()
        if response.status!=200:raise RuleError(f'Feed returned HTTP {response.status}; redirects are not followed.')
        if 'application/json' not in response.getheader('Content-Type',''):raise RuleError('Feed must return application/json.')
        data=response.read(2*1024*1024+1)
        if len(data)>2*1024*1024:raise RuleError('Feed response exceeds 2 MB.')
        return data
    finally:client.close()
