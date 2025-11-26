#!/usr/bin/env python
# -*- coding: utf8 -*-

import sys
import os
import urllib.request, urllib.parse, urllib.error
import chardet
from urllib.parse import urljoin, urlparse
from bs4 import UnicodeDammit
from lxml.html import fromstring, etree
import lxml.etree
import feedparser
import logging
import requests
import urllib3
from .extractor import FeedExtractor
from .consts import FEED_CONTENT_TYPES

# Suppress InsecureRequestWarning for unverified HTTPS requests
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def decode_html(html_string):
    converted = UnicodeDammit(html_string)
    return converted.unicode_markup


def get_url_data(url):
    """Extract HTML data from URL"""
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()  # Raise an exception for bad status codes
        realurl = r.url
        data = r.content  # Use this instead of urllib
        data = decode_html(data)
        # Use memory-efficient parser that removes blank text nodes
        parser = etree.HTMLParser(remove_blank_text=True)
        root = fromstring(data, parser=parser)
        return root, realurl
    except KeyboardInterrupt:
        sys.exit(0)
    except requests.exceptions.RequestException as e:
        logging.warning(f"Request error while fetching {url}: {e}")
        return None, None
    except (ValueError, lxml.etree.ParserError, lxml.etree.XMLSyntaxError) as e:
        logging.warning(f"Failed to parse HTML from {url}: {e}")
        return None, None
    except Exception as e:
        logging.warning(f"Unexpected error while processing {url}: {e}")
        return None, None


class FeedsFinder:
    """Look up for feeds on website pages"""

    def __init__(self):
        self.feedext = FeedExtractor()
        pass

    def __find_rss_autodiscover(self, root, url):
        """Autodiscover feeds by link"""
        feeds = []
        links = root.xpath("//link")
        logging.info(links)
        for link in links:
            if "rel" in link.attrib and link.attrib["rel"].lower() == "alternate":
                item = {}
                item["url"] = link.attrib["href"]
                if "type" in link.attrib:
                    ltype = link.attrib["type"].lower()
                    if ltype == "application/atom+xml":
                        item["feedtype"] = "atom"
                    elif ltype == "application/rss+xml":
                        item["feedtype"] = "rss"
                    else:
                        continue
                if "title" in link.attrib:
                    item["title"] = link.attrib["title"]
                item["confidence"] = 1
                feeds.append(item)
        return feeds

    def __find_feed_img(self, root, url):
        """Find by RSS image"""
        feeds = []
        for img in root.xpath("//img"):
            if "src" in img.attrib:
                href = img.attrib["src"]
                up = urlparse(href)
                ipath = up.path
                parts = ipath.split("/")
                parts.reverse()
                if len(parts) > 1:
                    name = parts[0] if len(parts[0]) > 0 else parts[1]
                else:
                    name = parts[0]
                name = name.lower()
                for k in ["rss", "feed"]:
                    if name.find(k) == 0 and name.find("feedback") == -1:
                        atag = img.getparent()
                        if atag.tag == "a":
                            u = atag.attrib["href"]
                            if u not in feeds:
                                item = {"url": u}
                                text = None
                                if "title" in atag.attrib:
                                    text = atag.attrib["title"]
                                if not text and "alt" in atag.attrib:
                                    text = atag.attrib["alt"]
                                if not text and "title" in img.attrib:
                                    text = img.attrib["title"]
                                if not text and "alt" in img.attrib:
                                    text = img.attrib["alt"]
                                if text is not None:
                                    item["title"] = text
                                if k == "rss":
                                    item["feedtype"] = "rss"
                                else:
                                    item["feedtype"] = "undefined"
                                item["confidence"] = 0.5
                                feeds.append(item)
        return feeds

    def __find_feed_by_urls(self, root, url):
        "Find feeds by related urls"
        feeds = []
        for olink in root.xpath("//a"):
            item = {}
            feedfound = False
            if "href" in olink.attrib:
                href = olink.attrib["href"]
                up = urlparse(href)
                ipath = up.path
                parts = ipath.split("/")
                parts.reverse()
                if len(parts) > 1:
                    name = parts[0] if len(parts[0]) > 0 else parts[1]
                else:
                    name = parts[0]
                name = name.lower()
                if name.find(".") > -1:
                    name, ext = name.rsplit(".", 1)
                else:
                    ext = ""
                for k in ["rss", "feed"]:
                    if name.find(k) == 0 and name.find("feedback") == -1:
                        u = olink.attrib["href"]
                        if u not in feeds:
                            item["url"] = u
                            if k == "rss":
                                item["feedtype"] = "rss"
                            else:
                                item["feedtype"] = "undefined"
                            item["confidence"] = 0.5
                            feeds.append(item)
                            feedfound = True
                            break
                if feedfound:
                    continue
                for p in parts:
                    if p in ["rss", "feed"]:
                        u = olink.attrib["href"]
                        if u not in feeds:
                            item["url"] = u
                            if p == "rss":
                                item["feedtype"] = "rss"
                            else:
                                item["feedtype"] = "undefined"
                            item["confidence"] = 0.5
                            feeds.append(item)
                            feedfound = True
                            break
                if feedfound:
                    continue
                try:
                    text = olink.text if olink.text else None
                except (AttributeError, TypeError) as e:
                    logging.debug(f"Error accessing link text: {e}")
                    text = None
                if text:
                    if text.lower().find("rss") > -1:
                        u = olink.attrib["href"]
                        if u not in feeds:
                            item["url"] = u
                            item["confidence"] = 0.5
                            item["feedtype"] = "rss"
                            feeds.append(item)
                            feedfound = True
                            break
                if feedfound:
                    continue
                for k in ["rss", "xml"]:
                    if ext.find(k) == 0:
                        if olink.getparent().tag == "a":
                            u = olink.attrib["href"]
                            if u not in feeds:
                                item["url"] = u
                                if k == "rss":
                                    item["feedtype"] = "rss"
                                else:
                                    item["feedtype"] = "undefined"
                                item["confidence"] = 0.5
                                feeds.append(item)
                                feedfound = True
                                break
                if feedfound:
                    continue
        return feeds

    def collect_feeds(self, root, url):
        url_set = set()  # Use set for O(1) lookups
        feeds = []
        
        for f in self.__find_rss_autodiscover(root, url):
            if f["url"] not in url_set:
                url_set.add(f["url"])
                feeds.append(f)
        
        for u in self.__find_feed_img(root, url):
            if u["url"] not in url_set:  # O(1) lookup
                url_set.add(u["url"])
                feeds.append(u)
        
        for u in self.__find_feed_by_urls(root, url):
            if u["url"] not in url_set:  # O(1) lookup
                url_set.add(u["url"])
                feeds.append(u)
        
        res = []
        for f in feeds:
            f["url"] = urljoin(url, f["url"])
            res.append(f)
        return res

    def find_feeds(
        self,
        url,
        noverify=True,
        force_htmlparse=False,
        include_entries=False,
        extractrss=False,
        crawl=False,
        timeout=30,
    ):
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
        try:
            r = requests.get(url, timeout=timeout)
            r.raise_for_status()  # Raise an exception for bad status codes
        except requests.exceptions.RequestException as e:
            logging.error(f"Failed to fetch {url}: {e}")
            return {"url": url, "items": []}
        
        real_url = r.url
        results = {"url": real_url, "items": items}
        
        # Check if content-type header exists
        content_type = r.headers.get("content-type", "").split(";")[0].strip()
        if content_type in FEED_CONTENT_TYPES:
            try:
                d = feedparser.parse(r.content)
            except Exception as e:
                logging.warning(f"Failed to parse feed from {url}: {e}")
                d = None
            
            if d and "title" in d.feed:
                item = {
                    "title": d.feed.title,
                    "url": real_url,
                    "feedtype": "rss",
                    "num_entries": len(d.entries),
                }
                if "language" in d.feed:
                    item["language"] = d.feed.language
                if include_entries:
                    item["entries"] = d.entries
                items.append(item)
        else:
            # Use memory-efficient parser that removes blank text nodes
            try:
                parser = etree.HTMLParser(remove_blank_text=True)
                root = fromstring(r.content, parser=parser)
            except (ValueError, lxml.etree.ParserError, lxml.etree.XMLSyntaxError) as e:
                logging.warning(f"Failed to parse HTML from {url}: {e}")
                root = None
            
            if root is not None:
                feeds = self.collect_feeds(root, real_url)
                for f in feeds:
                    if noverify:
                        item = {"title": f["url"], "url": f["url"], "feedtype": "rss"}
                        items.append(item)
                        continue
                    else:
                        try:
                            d = feedparser.parse(f["url"])
                        except Exception as e:
                            logging.warning(f"Failed to parse feed from {f['url']}: {e}")
                            d = None
                        
                        if d and "title" in d.feed:
                            item = {
                                "title": d.feed.title,
                                "url": f["url"],
                                "feedtype": f["feedtype"],
                                "num_entries": len(d.entries),
                            }
                            if "language" in d.feed:
                                item["language"] = d.feed.language
                            if include_entries:
                                item["entries"] = d.entries
                            items.append(item)
                        elif force_htmlparse:
                            try:
                                rp = requests.get(f["url"], timeout=timeout)
                                rp.raise_for_status()
                            except requests.exceptions.RequestException as e:
                                logging.warning(f"Failed to fetch {f['url']} for HTML parsing: {e}")
                                continue
                            
                            if not rp.content:
                                continue
                            
                            try:
                                parser = etree.HTMLParser(remove_blank_text=True)
                                root_content = fromstring(rp.content, parser=parser)
                                if root_content is None:
                                    continue
                                cfeeds = self.collect_feeds(root_content, rp.url)
                            except (ValueError, lxml.etree.ParserError, lxml.etree.XMLSyntaxError) as e:
                                logging.warning(f"Failed to parse HTML from {f['url']}: {e}")
                                continue
                            for cf in cfeeds:
                                if cf["url"] in feed_urls:
                                    continue
                                try:
                                    d = feedparser.parse(cf["url"])
                                except Exception as e:
                                    logging.warning(f"Failed to parse feed from {cf['url']}: {e}")
                                    continue
                                
                                if d and "title" in d.feed:
                                    item = {
                                        "title": d.feed.title,
                                        "url": f["url"],
                                        "feedtype": f["feedtype"],
                                        "num_entries": len(d.entries),
                                    }
                                    if "language" in d.feed:
                                        item["language"] = d.feed.language
                                    if include_entries:
                                        item["entries"] = d.entries
                                    items.append(item)
                if extractrss:
                    try:
                        datafeed, session = self.feedext.get_feed(r.url, data=r.content)
                    except Exception as e:
                        logging.warning(f"Failed to extract feed from {r.url}: {e}")
                        datafeed = None
                    
                    if datafeed and len(datafeed.get("items", [])) > 0:
                        item = {
                            "feedtype": "html",
                            "title": datafeed["title"],
                            "num_entries": len(datafeed["items"]),
                            "url": r.url,
                        }
                        if include_entries:
                            item["entries"] = datafeed["entries"]
                        items.append(item)
                results["items"] = items
        return results

    def find_feeds_deep(self, url, lookin=True):
        items = []
        root, real_url = get_url_data(url)
        results = {"url": real_url, "items": items}
        if not root:
            return {}
        feeds = self.collect_feeds(root, real_url)
        for f in feeds:
            try:
                d = feedparser.parse(f["url"])
            except Exception as e:
                logging.warning(f"Failed to parse feed from {f['url']}: {e}")
                d = None
            
            if d and "title" in d.feed:
                items.append(
                    {"title": d.feed.title, "url": f["url"], "feedtype": f["feedtype"]}
                )
            elif lookin:
                dp, dp_url = get_url_data(f["url"])
                if not dp:
                    results["items"] = items
                    return results
                cfeeds = self.collect_feeds(dp, dp_url)
                for cf in cfeeds:
                    try:
                        d = feedparser.parse(cf["url"])
                    except Exception as e:
                        logging.warning(f"Failed to parse feed from {cf['url']}: {e}")
                        continue
                    
                    if d and "title" in d.feed:
                        items.append(cf)
        results["items"] = items
        return results
