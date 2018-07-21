#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Tag mapping routines. Initially it was created for other purposes. It's intended to create web page map of tags, annotating
"""


from lxml import etree
import hashlib

from .consts import TAG_TYPE_BOLD, TAG_TYPE_EMPTY, TAG_TYPE_DATE, TAG_TYPE_HREF, TAG_TYPE_IMG, TAG_TYPE_LAST, TAG_TYPE_TAIL, TAG_TYPE_TEXT, TAG_TYPE_WRAPPER

class TagPath:
    """Tag path class. Allows unique tag identification"""

    def __init__(self, node, limit=None):
        self.__shifts = []
        self.__tag_names = []
        self.limit = limit

        self.__parseNode(node, limit)

    @staticmethod
    def getSharedNode(left, right, upToRelated=True):
        """Looks for shared parent for left and right nodes. upToRelated as True means using upper tag if shared tag is tbody"""
        l_path = TagPath(left)
        r_path = TagPath(right)
        change = l_path.level - r_path.level
        p_1 = left.getparent()
        p_2 = right.getparent()
        if change > 0:
            for i in range(0, change):
                p_1 = p_1.getparent()
        elif change < 0:
            for i in range(0, change):
                p_2 = p_2.getparent()
        while p_1 is not None and p_2 is not None:
            if p_1 == p_2:
                if upToRelated and p_1.tag == 'tbody':
                    p_1 = p_1.getparent()
                return p_1
            p_1 = p_1.getparent()
            p_2 = p_2.getparent()
        return None

    @staticmethod
    def getSharedPath(left, right):
        """Returns node root for two other nodes"""
        node = TagPath.getSharedNode(left, right)
        if node:
            return TagPath(node)
        return None

    def __parseNode(self, node, limit, inprogress=False):
        """Parses node to the tag path"""
        parent = node.getparent()
        if parent is not None and parent.tag != '<DOCUMENT_ROOT>' and node != limit:
            self.__shifts.append(parent.index(node))
            self.__tag_names.append(node.tag)
            self.__parseNode(parent, limit, inprogress=True)
        else:
            self.__shifts.append(0)
            self.__tag_names.append(node.tag)
        self.level = len(self.__shifts)
        if not inprogress:
            self.__shifts.reverse()
            self.__tag_names.reverse()
        self.key = '_'.join(map(str, self.__shifts))
        md = hashlib.md5()
        md.update(self.key.encode('utf8') if type(self.key) == type(u'') else self.key)
        self.hash = md.hexdigest()

    def __cmp__(self, tagpath):
        if list(self.values()) == list(tagpath.values()) and self.limit == tagpath.limit:
            return True
        return False

    def values(self):
        """Returns num of tag shifts, tag deepness"""
        return self.__shifts

    def key_values(self):
        """Returns list of values as unique key"""
        return '_'.join(map(str, self.__shifts))

    def tag_names(self):
        """Returns list of tag names"""
        return self.__tag_names

    def as_xpath(self):
        """Return path as xpath from root node"""
        tnames = self.__tag_names
        #        tnames.reverse()
        vals = self.__shifts
        #        vals.reverse()

        results = []
        i = 0
        results.append('//html')  # lxml hack to support DOCUMENT_ROOT
        for i in range(0, len(tnames)):
            results.append('/%s[%d]' % ('*', vals[i] + 1))
            i += 1
        return ''.join(results)


class TagEntry:
    """Tag record used to map tags to entities"""
    def __init__(self, aid, node, tag, position, path, parent_id, attrs=None, htmlattrs=None):
        if not attrs:
            attrs = []
        self.__id = aid
        self.node = node
        self.path = path
        self.tag = tag
        self.position = position
        self.parent_id = parent_id
        self.attrs = attrs
        self.htmlattrs = htmlattrs

    def as_list(self):
        return [self.__id, self.path.key_values(), self.tag, self.position, self.parent_id, self.attrs, self.htmlattrs]

class TagBlock:
    """Block of tags"""
    def __init__(self, root_node, path, position, shift):
        self.path = path
        self.__root_node = root_node
        self.position = position
        self.shift = shift
        self.entities = {}
        self.global_id = -1

    def add_entity(self, key, path, attr=None, value=None, b_value=None):
        self.entities[key] = [path, attr, value, b_value]

    def get_entities(self):
        return self.entities

    def as_dict(self):
        return {'position' : self.position, 'shift': self.shift, 'path' : self.path, 'entities' : self.entities}

    def as_html(self):
        if self.shift is None:
            return etree.tostring(self.__root_node.getchildren()[self.position], encoding='utf8')
        else:
            s = None
            ch = self.__root_node.getchildren()
            wlen = len(ch)
            for i in range(0, self.shift):
                if self.position + i < wlen:
                    if not s:
                        s = etree.tostring(ch[self.position + i], encoding='utf8')
                    else:
                        s += etree.tostring(ch[self.position + i], encoding='utf8')
            return s

    def identify_entities(self, node=None, parent_id=None):
        """Identifies tag entries as different data types"""
        annotations = []
        #        logging.info('Node: %s' %(str(node)))
        if node is None and self.shift is None:
            node = self.__root_node[self.position]
        elif node is None:
        #            logging.info(u'Root node: %s' %(unicode(self.__root_node)))
        #            logging.info(u'Position %d shift %d' %(self.position, self.shift))
        #            logging.info(u'Ch nodes: %s' %(unicode(self.__root_node.getchildren())))
        #            print len(self.__root_node.getchildren()[1].getchildren())
            for node in self.__root_node.getchildren()[self.position: self.position + self.shift]:
            #            print node
                if node is not None:
                    annotations.extend(self.identify_entities(node))
            return annotations
        #        logging.info('Node cor: %s' %(str(node)))
        ch = node
        ch_childs = ch.getchildren()
        attrs = []
        if ch.text and ch.tag not in ['script',] and len(ch.text.strip()) != 0:
            attrs.append(TAG_TYPE_TEXT)
        if ch.tail and len(ch.tail.strip()) != 0:
            attrs.append(TAG_TYPE_TAIL)
        if len(attrs) == 0:
            attrs.append(TAG_TYPE_EMPTY)
        if len(ch_childs) == 0:
            attrs.append(TAG_TYPE_LAST)
        elif len(ch_childs) == 1 and TAG_TYPE_EMPTY in attrs:
            attrs.append(TAG_TYPE_WRAPPER)
        if ch.tag == 'a' and 'href' in ch.attrib:
            attrs.append(TAG_TYPE_HREF)
        if ch.tag in ['h1', 'h2', 'h3', 'h4', 'b', 'strong']:
            attrs.append(TAG_TYPE_BOLD)
        if ch.tag == 'img' and 'src' in ch.attrib:
            attrs.append(TAG_TYPE_IMG)
        apath = TagPath(ch, self.__root_node)
        htmlattrs = dict(ch.attrib)
        self.global_id += 1
        aid = self.global_id
        annotations.append(TagEntry(aid, ch, ch.tag, ch.getparent().index(ch), apath, parent_id, attrs, htmlattrs))
        #       print 'Childs', ch_childs, ch
        #    logging.info('Node childs: %s' %(ch_childs))
        for child in ch_childs:
            if child is not None:
                annotations.extend(self.identify_entities(child, id))
            #                print 'Anns', annotations
        return annotations


    def print_block(self):
        """Prints this tag block"""
        if self.shift is None:
            print(etree.tostring(self.__root_node.getchildren()[self.position], encoding='utf8'))
        else:
            ch = self.__root_node.getchildren()
            for i in range(0, self.shift):
                print(etree.tostring(ch[self.position + i], encoding='utf8'))
