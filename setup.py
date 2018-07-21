import re
import io
from setuptools import setup, find_packages

open_as_utf = lambda x: io.open(x, encoding='utf-8')

(__version__, ) = re.findall("__version__.*\s*=\s*[']([^']+)[']",
                             open('newsworker/__init__.py').read())

readme = re.sub(r':members:.+|..\sautomodule::.+|:class:|:func:', '', open_as_utf('README.rst').read())
readme = re.sub(r'`Settings`_', '`Settings`', readme)
readme = re.sub(r'`Contributing`_', '`Contributing`', readme)
history = re.sub(r':mod:|:class:|:func:', '', open_as_utf('HISTORY.rst').read())



setup(
    name='newsworker',
    version=__version__,
    description=' Advanced news feeds extractor and finder library. Helps to automatically extract news from websites without RSS/ATOM feeds',
    long_description=readme + '\n\n' + history,
    author='Ivan Begtin',
    author_email='ivan@begtin.tech',
    url='https://github.com/ivbeg/newsworker',
    packages=find_packages(exclude=('tests', 'tests.*')),
    include_package_data=True,
    install_requires=[
        'pyparsing',
        'lxml',
        'bs4',
        'qddate'
    ],
    license="BSD",
    zip_safe=False,
    keywords='news parsing extraction feeds rss atom',
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Natural Language :: English',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: Implementation :: CPython',
        'Programming Language :: Python :: Implementation :: PyPy'
    ]
)
