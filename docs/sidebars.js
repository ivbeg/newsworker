/**
 * Creating a sidebar enables you to:
 - create an ordered group of docs
 - render a sidebar for each doc of that group
 - provide next/previous navigation
 */

// @ts-check

/** @type {import('@docusaurus/plugin-content-docs').SidebarsConfig} */
const sidebars = {
  docs: [
    {
      type: 'link',
      label: 'Contents',
      href: '/',
    },
    {
      type: 'category',
      label: 'Getting Started',
      items: [
        'getting-started/installation',
        'getting-started/quick-start',
        'getting-started/how-it-works',
        'getting-started/cookbook',
        'getting-started/basic-usage',
        'getting-started/performance',
        'getting-started/troubleshooting',
        'getting-started/best-practices',
      ],
    },
    {
      type: 'category',
      label: 'Use Cases',
      items: [
        'use-cases/html-to-feed',
        'use-cases/feed-discovery',
        'use-cases/local-feed-server',
        'use-cases/watch-and-delivery',
        'use-cases/batch-pipelines',
        'use-cases/parsing-specs',
      ],
    },
    {
      type: 'category',
      label: 'CLI Reference',
      items: [
        'commands/index',
        'commands/extract',
        'commands/serve',
        'commands/scan',
        'commands/analyze',
        'commands/batch',
        'commands/watch',
        'commands/cache',
        'commands/spec',
        'commands/parsedate',
      ],
    },
    {
      type: 'category',
      label: 'Guides',
      items: [
        'guides/output-formats',
        'guides/parsing-specs',
        'guides/settings',
        'guides/runtime-configuration',
        'guides/local-input',
        'guides/batch',
        'guides/discovery',
        'guides/diagnostics',
        'guides/undated',
        'guides/browser-rendering',
        'guides/language-support',
        'guides/delivery',
        'guides/security',
        'guides/migration-1-4',
      ],
    },
    {
      type: 'category',
      label: 'Integrations',
      items: [
        'integrations/python-library',
        'integrations/plugins-and-bridges',
        'integrations/docker',
        'integrations/feed-server',
      ],
    },
    {
      type: 'category',
      label: 'Development',
      items: [
        'development/contributing',
        'development/architecture',
        'development/openspec',
        'development/benchmarks',
      ],
    },
    'license',
  ],
};

module.exports = sidebars;
