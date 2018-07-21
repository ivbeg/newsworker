====================================================
newsworker -- automatic news extractor using HTML scraping
====================================================

.. image:: https://img.shields.io/travis/ivbeg/qddate/master.svg?style=flat-square
    :target: https://travis-ci.org/ivbeg/qddate
    :alt: travis build status

.. image:: https://img.shields.io/pypi/v/qddate.svg?style=flat-square
    :target: https://pypi.python.org/pypi/qddate
    :alt: pypi version

.. image:: https://readthedocs.org/projects/qddate/badge/?version=latest
    :target: http://qddate.readthedocs.org/en/latest/?badge=latest
    :alt: Documentation Status

.. image:: https://codecov.io/gh/scrapinghub/dateparser/branch/master/graph/badge.svg
   :target: https://codecov.io/gh/ivbeg/qddate
   :alt: Code Coverage

.. image:: https://badges.gitter.im/scrapinghub/dateparser.svg
   :alt: Join the chat at https://gitter.im/ivbeg/qddate
   :target: https://gitter.im/ivbeg/qddate?utm_source=badge&utm_medium=badge&utm_campaign=pr-badge&utm_content=badge


`newsworker` is a Python 3 lib that extracts feeds from html pages. It's useful when you need to subscribe to a news
from website that doesn't publish RSS/ATOM feeds and you don't want to use page change monitoring tools since it's not
so accurate.


Usage examples
---------------

Extract news from html page from EIB website and Bulgarian government website

    >>> feed, session = f.get_feed(url="http://government.bg/bg/prestsentar/novini")
    >>> feed
    ...


    >>> from newsworker.extractor import FeedExtractor
    >>> f = FeedExtractor(filtered_text_length=150)
    >>> feed, session = f.get_feed(url="http://www.eib.org/en/index.htm?lang=en")
    >>> feed
    {'title': 'European Investment Bank (EIB)', 'language': 'en', 'link': 'http://www.eib.org/en/index.htm?lang=en', 'description': 'European Investment Bank (EIB)', 'items': [{'title': 'Blockchain Challenge: coders at the EIB', 'description': 'Blockchain Challenge: coders at the EIB', 'pubdate': datetime.datetime(2018, 6, 18, 0, 0), 'unique_id': 'f9d359f76118076c5331ffec3cdb82eb', 'raw_html': b'<div class="first-column col-xs-12 col-sm-12 col-md-8 col-lg-8 no-padding-left-right"><div class="video-box no-padding-left-right"><a class="video-youtube" href="https://www.youtube.com/watch?v=YlKa2LZgxhE?autoplay=1"><div class="img-item-1" style="background-image:url(\'/img/movies/blockchain-video-hp.png\');"><span class="video-icon"><img height="100" src="/img/site/play.png" width="100"/></span><div class="video-container"><div class="left-box col-lg-8 col-xs-12"><div class="video-date-time"><small>18/06/2018</small><span class="space-separator"> | </span><small>02:12</small></div><div class="video-title col-xs-12 col-lg-12 no-padding-left-right">Blockchain Challenge: coders at the EIB</div></div></div></div></a></div></div>', 'extra': {'links': ['https://www.youtube.com/watch?v=YlKa2LZgxhE?autoplay=1'], 'images': ['http://www.eib.org/img/site/play.png']}, 'link': 'https://www.youtube.com/watch?v=YlKa2LZgxhE?autoplay=1'}, {'title': 'A brighter life for Kenyan women', 'description': 'Jujuy Verde â€“ new horizons for women waste-pickers in Argentina', 'pubdate': datetime.datetime(2018, 6, 5, 0, 0), 'unique_id': '9caef61535352d2734d122c0e092b011', 'raw_html': b'<div class="second-column col-xs-12 col-sm-12 col-md-4 col-lg-4 no-padding-left-right"><div class="video-box no-padding-left-right"><a class="video-youtube  fancybox.iframe" href="https://www.youtube.com/watch?v=T_7OmSDSXtc?autoplay=1"><div class="img-item-2" style="background-image:url(\'/img/kenya-dlight-video-hp.png\');"><span class="video-icon"><img height="100" src="/img/site/play.png" width="100"/></span><div class="video-container"><div class="left-box col-lg-8 col-xs-12"><div class="video-date-time"><small>04/06/2018</small><span class="space-separator"> | </span><small>01:32</small></div><div class="video-title col-xs-12 col-lg-12 no-padding-left-right">A brighter life for Kenyan women</div></div></div></div></a></div><div class="video-box no-padding-left-right"><a class="video-youtube fancybox.iframe" href="https://www.youtube.com/watch?v=d-btxsYT9hI?autoplay=1"><div class="img-item-3" style="background-image:url(\'/img/jujuy-video-hp.png\');"><span class="video-icon"><img height="100" src="/img/site/play.png" width="100"/></span><div class="video-container"><div class="left-box col-lg-8 col-xs-12"><div class="video-date-time"><small>05/06/2018</small><span class="space-separator"> | </span><small>03:12</small></div><div class="video-title col-xs-12 col-lg-12 no-padding-left-right">Jujuy Verde \xc3\xa2\xe2\x82\xac\xe2\x80\x9c new horizons for women waste-pickers in Argentina</div></div></div></div></a></div></div>', 'extra': {'links': ['https://www.youtube.com/watch?v=T_7OmSDSXtc?autoplay=1', 'https://www.youtube.com/watch?v=d-btxsYT9hI?autoplay=1'], 'images': ['http://www.eib.org/img/site/play.png']}, 'link': 'https://www.youtube.com/watch?v=T_7OmSDSXtc?autoplay=1'}], 'cache': {'pats': ['dt:date:date_1']}}

Reuse cached patterns to speed up further news extraction. It could greatly improve page parsing speed since it minimizes number of date comparsion up to 100x times
(2-3 date patterns instead of 350 patterns)
    >>> pats = feeds['cache']['pats']
    >>> feed, session = f.get_feed(url="http://www.eib.org/en/index.htm?lang=en", cached_p=pats)

Change user agent if needed
    >>> USER_AGENT = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.11 (KHTML, like Gecko) Chrome/23.0.1271.64 Safari/537.11'
    >>> feed, session = f.get_feed(url="http://www.eib.org/en/index.htm?lang=en", user_agent=USER_AGENT)


Initialize feed finder on webpage
    >>> from newsworker.finder import FeedsFinder
    >>> f = FeedsFinder()
Try to extract feeds if no one feed exists
    >>> feeds = f.find_feeds('http://government.bg/bg/prestsentar/novini')
    {'url': 'http://government.bg/bg/prestsentar/novini', 'items': []}

Add "extractrss" param launches FeedExtractor
    >>> feeds = f.find_feeds('http://government.bg/bg/prestsentar/novini', extractrss=True)
    >>> feeds
    {'url': 'http://government.bg/bg/prestsentar/novini', 'items': [{'feedtype': 'html', 'title': 'Министерски съвет :: Новини', 'num_entries': 12, 'url': 'http://government.bg/bg/prestsentar/novini'}]}

Find all feeds and more info from feeds. With "noverify=False" each feed parsed
    >>> feeds = f.find_feeds('https://www.dta.gov.au/news/', noverify=False)
    >>> feeds
    {'url': 'https://www.dta.gov.au/news/', 'items': [{'title': 'Digital Transformation Agency', 'url': 'https://www.dta.gov.au/feed.xml', 'feedtype': 'rss', 'num_entries': 10}]}

Addind "include_entries=True" returns feeds and all parsed feed entries
    >>> feeds = f.find_feeds('https://www.dta.gov.au/news/', noverify=False, include_entries=True)
    >>> feeds



Documentation
=============

Documentation is built automatically and can be found on
`Read the Docs <https://qddate.readthedocs.org/en/latest/>`_.


Features
========

* Identifies news blocks on webpages using date patterns. More than 348 date patterns supported. Uses <https://github.com/ivbeg/qddate>
* Extremely fast, uses pyparsing
* Includes function to find feeds on html page and if no feed found, than extract news

Limitations
========

* Not all language-specific dates supported
* Right aligned dates like "Published - 27-01-2018" not supported. It's not hard to add it but it greatly increases false acceptance rate.
* Some news pages has no dates with urls or texts. These pages are not supported yet

Speed optimization
========

* qddate <https://github.com/ivbeg/qddate> date parsing lib was created for this algorithm. Right now pattern marching is really fast
* date patterns could be cached to speed up parsing speed for the same website
* feed finder without verification of feeds works fast, but if verification enabled than it's slowed down


TODO
====
* Support more date formats and improve qddate lib
* Support news pages without dates

Usage
=====

The easiest way is to use the `newsworker.FeedExtractor <#newsworker.FeedExtractor>`_ class,
and it's `get_feed` function.

.. automodule:: newsworker.extractor
   :members: FeedExtractor
.. automodule:: newsworker.finder
   :members: FeedsFinder


Dependencies
============

`newsworker` relies on following libraries in some ways:

  * qddate_ is a module for data processing
.. _qddate: https://pypi.python.org/pypi/qddate
  * pyparsing_ is a module for advanced text processing.
.. _pyparsing: https://pypi.python.org/pypi/pyparsing
  * lxml is a module for xml parsing.
.. _lxml: https://pypi.python.org/pypi/lxml


Supported languages specific dates
==================================
* Bulgarian
* Czech
* English
* French
* German
* Portuguese
* Russian
* Spanish

Thanks
======
I wrote this news extraction code at 2008 year and later only updated it several times, migrating from regular expressions
to pyparsing. Initial project was divided between qddate date parsing lib and newsworker intended to news identification
on html pages

Feel free to ask question ivan@begtin.tech

.. image:: https://badges.gitter.im/newsworker/Lobby.svg
   :alt: Join the chat at https://gitter.im/newsworker/Lobby
   :target: https://gitter.im/newsworker/Lobby?utm_source=badge&utm_medium=badge&utm_campaign=pr-badge&utm_content=badge
