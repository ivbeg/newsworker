#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Persimmon News2RSS
http://persimmon-project.org

Persimmon News 2 RSS conversion

uses logging, lxml, django feedgenerator
"""

import logging
logging.getLogger().addHandler(logging.StreamHandler())

import hashlib
from copy import copy
import datetime
import requests
from lxml.html import fromstring
from pprint import PrettyPrinter
from lxml import etree
from qddate import DateParser
from .tools import get_abs_url, decode_html, clean_url, Logger
from .tagmapper import TagPath, TagBlock, TAG_TYPE_DATE, TAG_TYPE_TAIL, TAG_TYPE_TEXT, TAG_TYPE_HREF, TAG_TYPE_IMG

class FeedExtractor:
    """Feed Extraction class"""
    def __init__(self, debug=True, patterns=None, filtered_text_length=50):
        """

        :param patterns:List of patterns to use as rules
        """
        self.log = Logger()
        self.debug = debug
        self.log.save('initclass', 'Start loading patterns')
        self.indexer = DateParser(generate=True)
        self.log.save('initclass', 'End loading patterns')
        # key parameters
        self.filtered_text_length = filtered_text_length

        self.session = None

    def initfeed(self, document, base_url):
        """Inits feed to get data"""
        t_nodes = document.xpath('//head/title')
        if len(t_nodes) > 0 and t_nodes[0].text is not None:
            feed_title = t_nodes[0].text.strip()
            title_extracted = True
        else:
            feed_title = 'News from ' + base_url
            title_extracted = False
        # FIXME! default language should be page language based not just english by default. Not yet implemented
        feed = {'title' : feed_title, 'language' : 'en', 'link' : base_url, 'description' :feed_title, 'items' : []}
        if self.session:
            self.session['debug']['title_extracted'] =  title_extracted
        self.log.save('initfeed', 'Feed parsed')
        return feed

    def match_text(self, text):
        """Matches text to the regular expressions"""
        if text is None:
            return False, None, None, None
        res = self.indexer.match(text)
#        print('Compare %s ' % (text))
        self.session['debug']['num_textcompared'] += 1
#        self.log.save('match_text', 'Text %s against patterns, result %s' % (text, str(p)))
        if res:
            r = res['values']
            p = res['pattern']
            d = {'month' : 0, 'day' : 0, 'year' : 0}
            if 'noyear' in p and p['noyear'] == True:
                d['year'] = datetime.datetime.now().year
            for k, v in list(r.items()):
                d[k] = int(v)
            try:
                the_date = datetime.datetime(**d)
                self.session['debug']['num_matched'] += 1
                return True, p['key'], p, text, the_date
            except:
                return False, None, None, None
        return False, None, None, None

    def match_date(self, node):
        """Matches date to regular expressions. Uses  node as parameter"""
        if node is None:
            return None, None, None, None, None
        text_1 = None
        text_2 = None

        if node.text is not None and len(node.text.strip()) > 0:
            text_1 = str(node.text.strip('/\\«[]»').strip().replace('\xA0', ' '))
        if node.tail is not None and len(node.tail.strip()) > 0:
            text_2 = str(node.tail.strip('/\\«[]»').strip().replace('\xA0', ' '))
        if text_1 is None and text_2 is None:
            return None, None, None, None, None
#        self.log.save('match_date', 'Matching date text: ' + unicode(text_1))
#        self.log.save('match_date', 'Matching date tail: ' + unicode(text_2))
        if text_1 is not None:
            results = self.match_text(text_1)
            if results[0] is True:
                self.session['debug']['num_datematched'] += 1
                return results
        if text_2 is not None:
            results = self.match_text(text_2)
            if results[0] is True:
                self.session['debug']['num_datematched'] += 1
                return results
        return None, None, None, None, None

    def getclusters(self, document, base_url):
        """
        Extracts all available text nodes with fixed text length
        :param document: original document, result of lxml parse
        :param base_url: base url of the processed webpage
        :return:
        """
        nodes = document.xpath('//*[string-length(text())<%d]' % self.filtered_text_length )
        self.session['debug']['num_nodes'] = len(nodes)
        self.log.save('getclusters', 'Nodes extracted')
        shared_node = None
        last = None
        last_d = {}
        last_path = None
        clusters = {}
        first = True
        for node in nodes:
            (match, t_key, t_data, the_text, the_date) = self.match_date(node)
            if match:
                path = TagPath(node)
                if last is not None:
                    if path.level == last_path.level:
                        snode = TagPath.getSharedNode(node, last)
                        if shared_node is None:
                            shared_node = snode
                        spath = document.getroottree().getpath(snode)
                        if spath not in list(clusters.keys()):
                            clusters[spath] = {'snode' : snode, 'nodes' : []}
                        if first:
                            clusters[spath]['nodes'].append(last_d)
                            first = False
                        clusters[spath]['nodes'].append({'t_key' : t_key, 'node' : node})

                last = node
                last_d = {'t_key' : t_key, 'node' : node}
                last_path = path
        self.session['debug']['num_clusters'] = len(clusters)
        self.session['debug']['clusters'] = clusters
        return clusters



    def process_clusters(self, base_url, clusters, feed):
        """Extracts information from single clusters
        :param base_url: base url
        :param clusters: list of clusters
        :param feed: feed
        """
        cache_block = {'pats' : []}
        self.log.save('process_clusters', 'Start cluster processing')
        self.session['debug']['tagblocks'] = []
        self.session['debug']['annotations'] = []
        for p, node_info in list(clusters.items()):
            snode = node_info['snode']
            nodes = node_info['nodes']
            data = []
            if snode.tag == 'table':
                chd = snode.getchildren()
                for ch in chd:
                    if ch.tag == 'tbody':
                        snode = ch
                        break
            snode_path = TagPath(snode)
            for nodeitem in nodes:
                node = nodeitem['node']
                path = TagPath(node, snode)
#                print path.tag_names(), path.values()
                vals = list(path.values())
#                if snode.tag == 'table':
#                    data.append(vals[2])
#                else:
                data.append(vals[1])
            res = []
            avg_diff = {}
            last_block = None
            for i in range(len(data)-1, -1, -1):
                if i != len(data)-1:
                    diff = data[i+1] - data[i]
                    if diff not in list(avg_diff.keys()):
                        avg_diff[diff] = 0
                    avg_diff[diff] += 1
                    block = TagBlock(snode, snode_path, data[i], diff)
                    (match, t_key, t_data, the_text, the_date) = self.match_date(nodes[i]['node'])
                    use_tail = (nodes[i]['node'].text is None)
                    text = nodes[i]['node'].text if not use_tail else nodes[i]['node'].tail
                    if text is not None:
                        block.add_entity('pub_date', TagPath(nodes[i]['node']), None, text.strip(), the_date)
                        res.append(block)
#                        print block
                else:
                    diff = len(snode.getchildren()) - data[i]
                    if len(data) > 1:
                        block = TagBlock(snode, snode_path, data[i], diff)
                    else:
                        block = TagBlock(snode, snode_path, data[i], None)
                    last_block = block
                    (match, t_key, t_data, the_text, the_date) = self.match_date(nodes[i]['node'])
                    if nodes[i]['node'].text:
                        block.add_entity('pub_date', TagPath(nodes[i]['node']), None, the_text.strip(), the_date)
                        pass
                    else:
                        use_tail = (nodes[i]['node'].text is None)
                        text = nodes[i]['node'].text if not use_tail else nodes[i]['node'].tail
                        if text is not None:
                            block.add_entity('pub_date', TagPath(nodes[i]['node']), None, text.strip(), the_date)
#                            print block
                            #res.append(block)
                            max_num = 0
                            akey = 0
            max_num = 0
            akey = 0
            for key, value in list(avg_diff.items()):
                if value > max_num:
                    akey = key
            if last_block.shift != akey:
                last_block.shift = akey
            res.reverse()
            res.append(last_block)
#            print res

            for block in res:
#                self.session['debug']['tagblocks'].append([block.as_html(), block.as_dict()])
                anns =  block.identify_entities()
                raw_anns = []
                for ann in anns:
                    raw_anns.append(ann.as_list())
#                self.session['debug']['annotations'].append(raw_anns)
                for ann in anns:
                    (match, key, t_data, the_text, the_date) = self.match_date(ann.node)
                    if match:
                        ann.attrs.append(TAG_TYPE_DATE)
                title = None
                description = None
                url = None
                links = []
                images = []
                the_date = None
                i = 0
                for ann in anns:
                    i += 1
                    if ann.node.tag is etree.Comment:
                        continue
                    if TAG_TYPE_TEXT in ann.attrs and TAG_TYPE_DATE not in ann.attrs:
                        if len(ann.node.text.strip()) > 10 and title is None:
                            title = ann.node.text.strip()
                        if description is None and title is not None and title != ann.node.text.strip() and len(ann.node.text) > 10:
                            description = ann.node.text.strip()
                        elif title is not None and description is not None and len(ann.node.text) > 10:
                            description += '\n' + ann.node.text.strip()
                    if TAG_TYPE_TAIL in ann.attrs:
                        if len(ann.node.tail.strip()) > 10 and title is None:
                            title = ann.node.tail.strip()
                        if description is None and title is not None and len(ann.node.tail) > 10:
                            description = ann.node.tail.strip()
                        elif title is not None and description is not None and len(ann.node.tail) > 10:
                            description += '\n' + ann.node.tail.strip()
                    if TAG_TYPE_HREF in ann.attrs and 'href' in ann.node.attrib:
                        clr = clean_url(get_abs_url(base_url, ann.node.attrib['href']))
                        if clr not in links:
                            links.append(clr)
                    if TAG_TYPE_IMG in ann.attrs and 'src' in ann.node.attrib:
                        clr = clean_url(get_abs_url(base_url, ann.node.attrib['src']))
                        if clr not in images:
                            images.append(clr)

                    if TAG_TYPE_DATE in ann.attrs:
                        the_date = ann.node
                if title is not None and description is None:
                    description = title
                (match, t_key, t_data, the_text, a_date) = self.match_date(the_date)
                if match is None:
                    continue
                if not block.entities:
                    continue
                if t_key not in cache_block['pats']: cache_block['pats'].append(t_key)
                md = hashlib.md5()
                md.update(block.entities['pub_date'][2].encode('utf8'))
                if title:
                    md.update(title.encode('utf8'))
                if description:
                    md.update(description.encode('utf8'))
                if url:
                    md.update(url.encode('utf8'))
                ahash = md.hexdigest()
                item = {'title' : title,  'description' : description, 'pubdate' : a_date, 'unique_id': str(ahash), 'raw_html' : block.as_html()}
                item['extra'] = {'links' : links, 'images': images}
                if len(links) > 0:
                    item['link'] = clean_url(get_abs_url(base_url, links[0]))
                else:
                    item['link'] = clean_url(base_url)

                feed['items'].append(item)
        feed['cache'] = cache_block
        self.log.save('process_clusters', 'End cluster processing')
        return feed

    def fetch(self, url, user_agent=None):
        if user_agent is not None:
            headers = {'User-agent' : user_agent}
            u = requests.get(url, headers=headers)
        else:
            u = requests.get(url)
        data = u.content
        self.session['debug']['page_length'] = len(data)
        return data

    def init_session(self):
        """Used to start internal debugging session"""
        self.session = {'debug' : {'num_textcompared' : 0, 'num_matched' : 0, 'num_datematched' : 0}, 'params' : {}}
        self.session['debug']['num_patterns'] = len(self.indexer.patterns)


    def clear_session(self):
        """Used to end internal debugging section"""
        session = copy(self.session)
        session['log'] = self.log.getlogs()
        self.log.reset()
        self.session = None
        return session



    def get_feed(self, url, data=None, user_agent=None, cached_p=None):
        """Return feed from url"""
        self.init_session()
        if cached_p is not None:
            self.indexer.startSession(cached_p)
        if data is None:
            data = self.fetch(url, user_agent)
            self.log.save('get_rss', 'Url fetched %s' % (url))
        edata = decode_html(data)
        self.log.save('get_rss', 'Decode data')
        try:
            document = fromstring(edata)
        except ValueError:
            document = None
        self.log.save('get_rss', 'Parsed data')
        feed = self.initfeed(document, url)
        clusters = self.getclusters(document, url)
        self.log.save('get_rss', 'Clusters extracted')
        feed = self.process_clusters(url, clusters, feed)
        if cached_p is not None:
            self.indexer.endSession()
        self.log.save('get_rss', 'End of log')
        session = self.clear_session()
        return feed, session





    def learn_feed(self, url, user_agent=None, data=None):
        """Get Feed from page content in data field without using cached data"""
        self.init_session()
        printer = PrettyPrinter()
        self.log.save('learn_rss_data', 'Download url')
        if data is None:
            data = self.fetch(url, user_agent)
        edata = decode_html(data)
        self.log.save('learn_rss_data', 'Decode data')
        try:
            document = fromstring(edata)
        except:
            document = None
        self.log.save('learn_rss_data', 'Parsed data')
        feed = self.initfeed(document, url)
        clusters = self.getclusters(document, url)
        self.log.save('learn_rss_data', 'Clusters %s' % (printer.pformat(clusters)))
        feed = self.process_clusters(url, clusters, feed)
        self.log.save('learn_rss_data', 'End of log')
        session = self.clear_session()
        return feed, session


