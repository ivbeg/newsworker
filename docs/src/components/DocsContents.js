import React from 'react';
import Link from '@docusaurus/Link';
import styles from './DocsContents.module.css';

const sections = [
  {
    title: 'Getting Started',
    to: '/getting-started/installation',
    description:
      'Install newsworker and extract a first feed from a news listing page.',
    links: [
      {label: 'Installation', to: '/getting-started/installation'},
      {label: 'Quick start', to: '/getting-started/quick-start'},
      {label: 'How it works', to: '/getting-started/how-it-works'},
      {label: 'Cookbook', to: '/getting-started/cookbook'},
      {label: 'Basic usage', to: '/getting-started/basic-usage'},
      {label: 'Performance', to: '/getting-started/performance'},
      {label: 'Troubleshooting', to: '/getting-started/troubleshooting'},
      {label: 'Best practices', to: '/getting-started/best-practices'},
    ],
  },
  {
    title: 'Use Cases',
    to: '/use-cases/html-to-feed',
    description:
      'End-to-end examples for extraction, discovery, watching, and batch work.',
    links: [
      {label: 'HTML to feed', to: '/use-cases/html-to-feed'},
      {label: 'Feed discovery', to: '/use-cases/feed-discovery'},
      {label: 'Local feed server', to: '/use-cases/local-feed-server'},
      {label: 'Watch and delivery', to: '/use-cases/watch-and-delivery'},
      {label: 'Batch pipelines', to: '/use-cases/batch-pipelines'},
      {label: 'Parsing specs', to: '/use-cases/parsing-specs'},
    ],
  },
  {
    title: 'CLI Reference',
    to: '/commands/',
    description:
      'Command-by-command reference for extract, serve, scan, analyze, and more.',
    links: [
      {label: 'All commands', to: '/commands/'},
      {label: 'extract', to: '/commands/extract'},
      {label: 'serve', to: '/commands/serve'},
      {label: 'scan', to: '/commands/scan'},
      {label: 'analyze', to: '/commands/analyze'},
      {label: 'batch', to: '/commands/batch'},
      {label: 'watch', to: '/commands/watch'},
    ],
  },
  {
    title: 'Guides',
    to: '/guides/output-formats',
    description:
      'Specs, formats, configuration, security, languages, and migration notes.',
    links: [
      {label: 'Output formats', to: '/guides/output-formats'},
      {label: 'Parsing specs', to: '/guides/parsing-specs'},
      {label: 'Settings', to: '/guides/settings'},
      {label: 'Runtime configuration', to: '/guides/runtime-configuration'},
      {label: 'Batch manifests', to: '/guides/batch'},
      {label: 'Security', to: '/guides/security'},
    ],
  },
  {
    title: 'Integrations',
    to: '/integrations/python-library',
    description:
      'Python library, plugins, site bridges, Docker, and the local feed server.',
    links: [
      {label: 'Python library', to: '/integrations/python-library'},
      {label: 'Plugins and bridges', to: '/integrations/plugins-and-bridges'},
      {label: 'Docker', to: '/integrations/docker'},
      {label: 'Feed server', to: '/integrations/feed-server'},
    ],
  },
  {
    title: 'Development',
    to: '/development/contributing',
    description:
      'Contributing, architecture, OpenSpec workflow, and benchmarks.',
    links: [
      {label: 'Contributing', to: '/development/contributing'},
      {label: 'Architecture', to: '/development/architecture'},
      {label: 'OpenSpec', to: '/development/openspec'},
      {label: 'Benchmarks', to: '/development/benchmarks'},
      {label: 'License', to: '/license'},
    ],
  },
];

function Section({title, to, description, links}) {
  return (
    <article className={styles.card}>
      <h2 className={styles.cardTitle}>
        <Link to={to}>{title}</Link>
      </h2>
      <p className={styles.cardDescription}>{description}</p>
      <ul className={styles.linkList}>
        {links.map((item) => (
          <li key={item.label}>
            {item.href ? (
              <a href={item.href}>{item.label}</a>
            ) : (
              <Link to={item.to}>{item.label}</Link>
            )}
          </li>
        ))}
      </ul>
    </article>
  );
}

export default function DocsContents() {
  return (
    <section className={`${styles.contents} container`}>
      <h2 className={styles.heading}>Documentation contents</h2>
      <p className={styles.intro}>
        Start with a section below, or use the sidebar from any page. The CLI
        entry point is <code>newsworker</code>.
      </p>
      <div className={styles.grid}>
        {sections.map((section) => (
          <Section key={section.title} {...section} />
        ))}
      </div>
    </section>
  );
}
