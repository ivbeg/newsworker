#!/usr/bin/env python
# -*- coding: utf8 -*-

import sys
import os
import urllib.request, urllib.parse, urllib.error
import urllib.request, urllib.error, urllib.parse
import chardet
from urllib.parse import urljoin, urlparse
from bs4 import UnicodeDammit
from lxml.html import fromstring, etree
import lxml.etree
import feedparser
import logging
import requests
from .extractor import FeedExtractor
from .consts import FEED_CONTENT_TYPES

def decode_html(html_string):
    converted = UnicodeDammit(html_string)
    return converted.unicode_markup


def get_url_data(url):
    realurl = None
    r = requests.get(url)
    try:
        f = urllib.request.urlopen(url)
        data = f.read()
        realurl = f.geturl()
        f.close()
    except KeyboardInterrupt:
        sys.exit(0)
    #        except :
    #            return None, None
    data = decode_html(data)
    try:
        root = fromstring(data)
    except ValueError:
        return None, None
    except lxml.etree.ParserError:
        return None, None
    return root, realurl


class FeedsFinder:
    """Look up for feeds on website pages"""
    def __init__(self):
        self.feedext = FeedExtractor()
        pass

    def __find_rss_autodiscover(self, root, url):
        """Autodiscover feeds by link"""
        feeds = []
        links = root.xpath('//link')
        logging.info(links)
        for link in links:
            if 'rel' in link.attrib and link.attrib['rel'].lower() == 'alternate':
                item = {}
                item['url'] = link.attrib['href']
                if 'type' in link.attrib:
                    ltype = link.attrib['type'].lower()
                    if ltype == 'application/atom+xml':
                        item['feedtype'] = 'atom'
                    elif ltype == 'application/rss+xml':
                        item['feedtype'] = 'rss'
                    else:
                        continue
                if 'title' in link.attrib: item['title'] = link.attrib['title']
                item['confidence'] = 1
                feeds.append(item)
        return feeds


    def __find_feed_img(self, root, url):
        """Find by RSS image """
        feeds = []
        for img in root.xpath('//img'):
            if 'src' in img.attrib:
                href = img.attrib['src']
                up = urlparse(href)
                ipath = up.path
                parts = ipath.split('/')
                parts.reverse()
                if len(parts) > 1:
                    name = parts[0] if len(parts[0]) > 0 else parts[1]
                else:
                    name = parts[0]
                name = name.lower()
                for k in ['rss', 'feed']:
                    if name.find(k) == 0 and name.find('feedback') == -1:
                        atag = img.getparent()
                        if atag.tag == 'a':
                            u = atag.attrib['href']
                            if u not in feeds:
                                item = {'url' : u}
                                text = None
                                if 'title' in atag.attrib: text = atag.attrib['title']
                                if not text and 'alt' in atag.attrib: text = atag.attrib['alt']
                                if not text and 'title' in img.attrib: text = img.attrib['title']
                                if not text and 'alt' in img.attrib: text = img.attrib['alt']
                                if text is not None: item['title'] = text
                                if k == 'rss': item['feedtype'] = 'rss'
                                else: item['feedtype'] = 'undefined'
                                item['confidence'] = 0.5
                                feeds.append(item)
        return feeds


    def __find_feed_by_urls(self, root, url):
        "Find feeds by related urls"
        feeds = []
        for olink in root.xpath('//a'):
            item = {}
            feedfound = False
            if 'href' in olink.attrib:
                href = olink.attrib['href']
                up = urlparse(href)
                ipath = up.path
                parts = ipath.split('/')
                parts.reverse()
                if len(parts) > 1:
                    name = parts[0] if len(parts[0]) > 0 else parts[1]
                else:
                    name = parts[0]
                name = name.lower()
                if name.find('.') > -1:
                    name, ext = name.rsplit('.', 1)
                else:
                    ext = ''
                for k in ['rss', 'feed']:
                    if name.find(k) == 0 and name.find('feedback') == -1:
                        u = olink.attrib['href']
                        if u not in feeds:
                            item['url'] = u
                            if k == 'rss':
                                item['feedtype'] = 'rss'
                            else:
                                item['feedtype'] = 'undefined'
                            item['confidence'] = 0.5
                            feeds.append(item)
                            feedfound = True
                            break
                if feedfound: continue
                for p in parts:
                    if p in ['rss', 'feed']:
                        u = olink.attrib['href']
                        if u not in feeds:
                            item['url'] = u
                            if p == 'rss':
                                item['feedtype'] = 'rss'
                            else:
                                item['feedtype'] = 'undefined'
                            item['confidence'] = 0.5
                            feeds.append(item)
                            feedfound = True
                            break
                if feedfound: continue
                try:
                    text = olink.text if olink.text else None
                except:
                    text = None
                if text:
                    if text.lower().find('rss') > -1:
                        u = olink.attrib['href']
                        if u not in feeds:
                            item['url'] = u
                            item['confidence'] = 0.5
                            item['feedtype'] = 'rss'
                            feeds.append(item)
                            feedfound = True
                            break
                if feedfound: continue
                for k in ['rss', 'xml']:
                    if ext.find(k) == 0:
                        if olink.getparent().tag == 'a':
                            u = olink.attrib['href']
                            if u not in feeds:
                                item['url'] = u
                                if k == 'rss':
                                    item['feedtype'] = 'rss'
                                else:
                                    item['feedtype'] = 'undefined'
                                item['confidence'] = 0.5
                                feeds.append(item)
                                feedfound = True
                                break
                if feedfound: continue
        return feeds



    def collect_feeds(self, root, url):
        urls = []
        feeds = self.__find_rss_autodiscover(root, url)
        for f in feeds:
            urls.append(f['url'])
        for u in self.__find_feed_img(root, url):
            if u['url'] not in urls:
                urls.append(u['url'])
                feeds.append(u)
        for u in self.__find_feed_by_urls(root, url):
            if u['url'] not in urls:
                urls.append(u['url'])
                feeds.append(u)
        res = []
        for f in feeds:
            f['url'] = urljoin(url, f['url'])
            res.append(f)
#        feeds = [urljoin(url, u) for f in feeds]
        return res


    def find_feeds(self, url, noverify=True, force_htmlparse=False, include_entries=False, extractrss=False, crawl=False):
        """
        :param url: webpage url
        :param noverify: Adds feeds without parsing. Warning, it's true by default. If you set it to false, it will be much slover
        :param force_htmlparse: Forces parse of found HTML links as RSS/ATOM
        :param include_entries: If "True" adds entries to the result
        :param extractrss: If "True" uses feed extract algorithm to get valid feed
        :param crawl: If "True" then crawls pages that are most likely with news. Not implemented yet
        :return: list of feeds
        """
        feed_urls = []
        items = []
        r = requests.get(url)
        real_url = r.url
        results = {'url': real_url, 'items': items}
        if r.headers['content-type'] in FEED_CONTENT_TYPES:
            d = feedparser.parse(r.content)
            if 'title' in d.feed:
                item = {'title': d.feed.title, 'url': real_url, 'feedtype': 'rss',
                        'num_entries': len(d.entries)}
                if 'language' in d.feed:
                    item['language'] = d.feed.language
                if include_entries:
                    item['entries'] = d.entries
                items.append(item)
        else:
            root = fromstring(r.content)
            if root is not None:
                feeds = self.collect_feeds(root, real_url)
                for f in feeds:
                    if noverify:
                        item = {'title': f['url'], 'url': f['url'], 'feedtype': 'rss'}
                        items.append(item)
                        continue
                    else:
                        d = feedparser.parse(f['url'])
                        if 'title' in d.feed:
                            item = {'title': d.feed.title, 'url': f['url'], 'feedtype': f['feedtype'], 'num_entries' : len(d.entries)}
                            if 'language' in d.feed:
                                item['language'] = d.feed.language
                            if include_entries:
                                item['entries'] = d.entries
                            items.append(item)
                        elif force_htmlparse:
                            rp = requests.get(f['url'])
                            if not rp.content:
                                continue
                            cfeeds = self.collect_feeds(rp.content, rp.url)
                            for cf in cfeeds:
                                if cf['url'] in feed_urls:
                                    continue
                                d = feedparser.parse(cf['url'])
                                item = {'title': d.feed.title, 'url': f['url'], 'feedtype': f['feedtype'],
                                        'num_entries': len(d.entries)}
                                if 'language' in d.feed:
                                    item['language'] = d.feed.language
                                if include_entries:
                                    item['entries'] = d.entries
                                items.append(item)
                if extractrss:
                    datafeed, session = self.feedext.get_feed(r.url, data=r.content)
                    if datafeed and len(datafeed['items']) > 0:
                        item = {'feedtype': 'html', 'title': datafeed['title'], 'num_entries': len(datafeed['items']), 'url': r.url}
                        if include_entries:
                            item['entries'] = datafeed['entries']
                        items.append(item)
                results['items'] = items
        return results

    def find_feeds_deep(self, url, lookin=True):
        items = []
        root, real_url = self.__get_page(url)
        results = {'url' : real_url, 'items' : items}
        if not root:
            return {}
        feeds = self.collect_feeds(root, real_url)
        for f in feeds:
            d = feedparser.parse(f['url'])
            if 'title' in d.feed:
                items.append({'title' : d.feed.title, 'url' : f['url'], 'feedtype' : f['feedtype']})
            elif lookin:
                dp, dp_url = self.__get_page(f['url'])
                if not dp:
                    results['items'] = items
                    return results
                cfeeds = self.collect_feeds(dp, dp_url)
                for cf in cfeeds:
                    d = feedparser.parse(cf['url'])
                    if 'title' in d.feed:
                        items.append(cf)
        results['items'] = items
        return results
