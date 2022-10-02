# -*- coding: utf8 -*-

from dataclasses import dataclass, List, field
from typing import List
from datetime import datetime
from feedgen.feed import FeedGenerator

@dataclass
class NewsItem:
    """News single item"""
    id: str
    title: str
    pubdate: datetime
    description: str = field(default=None)
    link: str = field(default=None)
    image: str = field(default=None)    
    raw_html: str = field(default=None)    


@dataclass
class NewsFeed:
    """News feed data class"""
    # Feed parameters 
    title: str
    logo: str = field(default=None)
    link: str = field(default=None)
    language: str = field(default='en')
    items: List[NewsItem] = field(default=[])

    # Feed parser attributes
    block_path: str = field(default=None)
    items_path: str = field(default=None)
    date_patterns: List[str] = field(default=None)
    items_have_link: bool = field(default=True) 
    items_have_image: bool = field(default=True)
    
    def as_atom(self, public_url=None):    
        """Export news feed as ATOM string"""
        fg = FeedGenerator()
        fg.id(self.id)
        fg.title(self.title)
#        fg.author( {'name':'John Doe','email':'john@example.de'} )
        if public_url:
            fg.link( href=public_url, rel='self' )
        fg.link( href=self.link, rel='alternate' )
        if self.logo:
            fg.logo(self.logo)
        fg.language(self.language)        
        for item in self.items:
            fe = fg.add_entry()
            fe.id(item.id)
            fe.title(item.title)
            fe.description(item.description)
            fe.link(item.link)
            fe.pubDate(item.pubdate)
        return fg.atom_str(pretty=True)