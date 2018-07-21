#!/usr/bin/env python
# -*- coding: utf-8 -*-
""" Usage is simple. Give it url and get the json
"""

import logging
logging.getLogger().addHandler(logging.StreamHandler())
import sys
from pprint import PrettyPrinter, pprint
import json
import datetime
from newsworker.extractor import FeedExtractor
from newsworker.finder import FeedsFinder

USER_AGENT = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.11 (KHTML, like Gecko) Chrome/23.0.1271.64 Safari/537.11'

date_handler = lambda obj: (
    obj.isoformat()
    if isinstance(obj, (datetime.datetime, datetime.date))
    else None
)


if __name__ == "__main__":
    if len(sys.argv) > 2:
        if sys.argv[1] == 'extract':
            ext = FeedExtractor(filtered_text_length=150)
            feed, session = ext.get_feed(sys.argv[2], user_agent=USER_AGENT)
            print(json.dumps(feed, indent=4, default=date_handler))
        elif sys.argv[1] == 'find':
            r = FeedsFinder().find_feeds(sys.argv[2], noverify=False)
            print('---')
            pprint(r)
        else:
            print('only "find" and "extract" commands supported')
    else:
        print("""Usage: feedcmd.py find <url> - to search feeds on web page
                  extract <url> - to extract news from html page\n""")
