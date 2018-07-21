# -*- coding: utf-8 -*-


# Tags constants
DATE_CLASSES_KEYWORDS = [x.lower() for x in ['news_date', 'news-date-time', 'date', 'news-date', 'newslistdate',
                'createdate', 'date_block', 'b_date', 'entry-date', 'pub_date', 'g-date',
                'post-date', 'textdate', 'datestamp', 'date-time', 'dateBlock', 'date-posted',
                'NewsDate', 'newsDate', 'artDate', 'gDate', 'postDate', 'pubDate', 'newsPubDate',
                'NewsDateTime', 'timestamp', 'publish_time', 'news_time', 'news-time', 'newsTime', 'newsdate', 'meta-date',
                'n_date', 'time_news', 'newsdatetime', 'date_time', 'g-time']]

DATE_CLASSES_KEYS = ['date', 'time']

NEWS_CLASSES_KEYWORDS = [x.lower() for x in ['news-item', 'news', 'latestnews', 'news_title', 'news-title', 'news_item', 'news-text', 'news-list',
'news_text', 'newstitle', 'mainnews', 'newslist', 'news-main', 'firstnews', 'news-link', 'newslink', 'newsblock', 'news-block',
'news-content', 'news_block', 'news-name', 'newsItem', 'newstext', 'news-ann', 'news_img', 'News', 'news_caption', 'newsTitle',
'item_news', 'news-picture', 'news_anons', 'novost']]

NEWS_CLASSES_KEYS = ['news', 'novost', 'novosti']

FEED_CONTENT_TYPES = ['application/rss+xml', 'application/rdf+xml', 'application/atom+xml',
                     'application/xml', 'text/xml']

TAG_TYPE_TEXT = 'tag:type:text'
TAG_TYPE_TAIL = 'tag:type:tail'
TAG_TYPE_WRAPPER = 'tag:type:wrapper'
TAG_TYPE_LAST = 'tag:type:last'
TAG_TYPE_EMPTY = 'tag:type:empty'
TAG_TYPE_HREF = 'tag:type:url'
TAG_TYPE_BOLD = 'tag:type:bold'    # Shows title type of texts
TAG_TYPE_IMG = 'tag:type:img'

TAG_TYPE_DATE = 'tag:type:date'

CLEANABLE_QUERY_KEYS = ['PHPSESSID', 'utm_source', 'utm_campaign', 'utm_medium', 'utm_content', 'utm_hp_ref']
