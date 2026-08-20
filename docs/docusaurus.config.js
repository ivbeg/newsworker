// @ts-check
// Note: type annotations allow type checking and IDEs autocompletion

const lightCodeTheme = require('prism-react-renderer').themes.github;
const darkCodeTheme = require('prism-react-renderer').themes.dracula;

/** @type {import('@docusaurus/types').Config} */
const config = {
  title: 'newsworker',
  tagline: 'Turn any news page into an RSS/Atom feed',
  favicon: 'img/favicon.svg',

  url: 'https://ivbeg.github.io',
  baseUrl: '/newsworker/',

  organizationName: 'ivbeg',
  projectName: 'newsworker',
  deploymentBranch: 'gh-pages',
  trailingSlash: false,

  onBrokenLinks: 'throw',
  markdown: {
    mermaid: true,
    hooks: {
      onBrokenMarkdownLinks: 'warn',
    },
  },
  themes: ['@docusaurus/theme-mermaid'],

  i18n: {
    defaultLocale: 'en',
    locales: ['en'],
  },

  presets: [
    [
      'classic',
      /** @type {import('@docusaurus/preset-classic').Options} */
      ({
        docs: {
          sidebarPath: require.resolve('./sidebars.js'),
          editUrl: 'https://github.com/ivbeg/newsworker/edit/master/docs/docs/',
          routeBasePath: '/',
        },
        blog: false,
        theme: {
          customCss: require.resolve('./src/css/custom.css'),
        },
      }),
    ],
  ],

  themeConfig:
    /** @type {import('@docusaurus/preset-classic').ThemeConfig} */
    ({
      image: 'img/logo.svg',
      navbar: {
        title: 'newsworker',
        logo: {
          alt: 'newsworker logo',
          src: 'img/logo.svg',
        },
        items: [
          {
            to: '/',
            label: 'Contents',
            position: 'left',
            activeBaseRegex: '^/newsworker/?$',
          },
          {
            type: 'docSidebar',
            sidebarId: 'docs',
            position: 'left',
            label: 'Docs',
          },
          {
            to: '/getting-started/cookbook',
            label: 'Cookbook',
            position: 'left',
          },
          {
            href: 'https://github.com/ivbeg/newsworker',
            label: 'GitHub',
            position: 'right',
          },
          {
            href: 'https://pypi.org/project/newsworker/',
            label: 'PyPI',
            position: 'right',
          },
        ],
      },
      footer: {
        style: 'dark',
        links: [
          {
            title: 'Docs',
            items: [
              {
                label: 'Contents',
                to: '/',
              },
              {
                label: 'Getting Started',
                to: '/getting-started/installation',
              },
              {
                label: 'CLI Reference',
                to: '/commands/',
              },
              {
                label: 'Cookbook',
                to: '/getting-started/cookbook',
              },
            ],
          },
          {
            title: 'Guides',
            items: [
              {
                label: 'Parsing specs',
                to: '/guides/parsing-specs',
              },
              {
                label: 'Output formats',
                to: '/guides/output-formats',
              },
              {
                label: 'Runtime configuration',
                to: '/guides/runtime-configuration',
              },
              {
                label: 'Security',
                to: '/guides/security',
              },
            ],
          },
          {
            title: 'Project',
            items: [
              {
                label: 'GitHub',
                href: 'https://github.com/ivbeg/newsworker',
              },
              {
                label: 'PyPI',
                href: 'https://pypi.org/project/newsworker/',
              },
              {
                label: 'Changelog',
                href: 'https://github.com/ivbeg/newsworker/blob/master/CHANGELOG.md',
              },
              {
                label: 'License',
                to: '/license',
              },
            ],
          },
        ],
        copyright: `Copyright © ${new Date().getFullYear()} Ivan Begtin. newsworker is MIT licensed.`,
      },
      prism: {
        theme: lightCodeTheme,
        darkTheme: darkCodeTheme,
        additionalLanguages: ['python', 'bash', 'yaml', 'json'],
      },
    }),
};

module.exports = config;
