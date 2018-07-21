#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Supportive functions to help news extraction algorithms
"""
from bs4 import UnicodeDammit
import time, datetime
from urllib.parse import urlparse, urljoin, parse_qs
from .consts import CLEANABLE_QUERY_KEYS


def decode_html(html_string):
    return UnicodeDammit(html_string).unicode_markup


def get_abs_url(root_url, url):
    """Returns absolute url"""
    https = False
#    print('Root url: %s and url: %s' % (root_url, url))
    if root_url[:7] == 'http://':
        o = urlparse(root_url)
    elif root_url[:8] == 'https://':
        o = urlparse(root_url)
        https = True
    else:
        o = urlparse('http://' + root_url)
        #    if url:
    #        o = urlparse.urlparse(root_url)
    if len(url) == 0:
        url = 'http://' + o.netloc
    if url[0] == '/':
        url = 'http://' + o.netloc + url
    elif url[:2] == './':
        url = root_url.rsplit('/', 1)[0] + url[1:]
    elif url[:7] != 'http://' and url[:8] != 'https://':
        if len(o.path) > 0 and o.path[len(o.path) - 1] == '/':
            if o.path[len(o.path) - 1] == '/':
                url = root_url + url
            else:
                parts = o.path.rsplit('/', 1)
                if len(parts) == 1:
                    url = root_url + '/' + url
                else:
                    if not https:
                        url = 'http://' + o.netloc + parts[0] + '/' + url
                    else:
                        url = 'https://' + o.netloc + parts[0] + '/' + url

    return url


def clean_url(url):
    """Removes just query parameters from url"""
    # clean url from jsession param
    THE_JS_KEY  = ';jsessionid='
    n = url.find(THE_JS_KEY)
    if n > -1:
        thepath = url[:n] + url[n+len(THE_JS_KEY) + 32:]
        url = thepath
    o = urlparse(url)

    # clean query
    if len(o.query) > 0:
        query = clean_urlquery(o.query)[0]
        if len(query) > 0:
            url = o.geturl().rsplit('?')[0] + '?' + query
        else:
            return o.geturl().rsplit('?')[0]
        return url
#    print o
    return o.geturl()

def clean_urlquery(qs):
    """Removes _junk_ query parameters left by analytics systems"""
    items = parse_qs(qs, keep_blank_values=True)
    results = {}
    filtered = {}
    for k, v in list(items.items()):
        if k.lower() not in CLEANABLE_QUERY_KEYS:
            results[k] = v
        else:
            filtered[k] = v
    q = []
    for k, v in list(results.items()):
        q.append('%s=%s' % (k, v[0]))
    query = '&'.join(q)
    return query, results, filtered



class Logger:
    def __init__(self, autostart=True):
        self.logs = []
        if autostart:
            self.reset()
        pass

    def reset(self):
        self.current = time.time()

    def clear(self):
        self.logs = []


    def save(self, code, msg, autoreset=True):
        current = time.time()
        record = {'dt' : datetime.datetime.now().isoformat(), 'time' : current - self.current, 'msg' : msg, 'code' : code}
        if autoreset:
            self.current = current
        self.logs.append(record)


    def getlogs(self):
        return self.logs
